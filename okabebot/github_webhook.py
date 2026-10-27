"""Signed GitHub events; no event text is interpreted as instructions."""

import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import threading
import time

from .adapters.github_checks import FAILURES


def configured_secret():
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        path = (
            Path(os.environ.get("OKABEBOT_CONFIG", "okabebot.local.json")).resolve().parent / ".env"
        )
        if path.is_file():
            for line in path.read_text().splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == "GITHUB_WEBHOOK_SECRET":
                    values = shlex.split(value.strip())
                    secret = values[0] if values else ""
    return secret


class GitHubWebhook:
    def __init__(self, inbox, repositories, secret=None):
        self.inbox = inbox
        self.repositories = set(repositories)
        self.secret = configured_secret() if secret is None else secret
        self.lock = threading.Lock()
        with inbox.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS github_deliveries (digest TEXT PRIMARY KEY,received REAL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS github_deployments (id TEXT PRIMARY KEY,repo TEXT,name TEXT,state TEXT,updated REAL,received REAL)"
            )

    def receive(self, headers, raw):
        if not self.secret or not self.repositories:
            raise PermissionError("GitHub webhooks are not configured")
        if len(raw) > 1_000_000:
            raise ValueError("Payload too large")
        signature = headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(self.secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise PermissionError("Invalid webhook signature")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Expected event object")
        event = headers.get("X-GitHub-Event", "")
        if event == "ping":
            return {"accepted": True, "ping": True}
        repo = payload.get("repository", {}).get("full_name", "")
        if repo not in self.repositories:
            raise PermissionError("Repository is not allowed")
        # Event identity comes from signed bytes, not an unsigned delivery header.
        digest = hashlib.sha256(raw).hexdigest()
        with self.lock:
            with self.inbox.connect() as db:
                if db.execute(
                    "SELECT 1 FROM github_deliveries WHERE digest=?", (digest,)
                ).fetchone():
                    return {"accepted": True, "duplicate": True}
            if event == "workflow_run":
                run = payload.get("workflow_run", {})
                if payload.get("action") == "completed" and run.get("conclusion") in FAILURES:
                    if type(run.get("id")) is not int or type(run.get("run_attempt", 1)) is not int:
                        raise ValueError("Workflow identity required")
                    self.inbox.publish(
                        "github",
                        ("Checks failed · " + str(run.get("name") or "Workflow"))[:100],
                        (repo + " · " + str(run.get("head_branch") or "detached"))[:500],
                        "important",
                        "workflow-" + str(run["id"]) + "-" + str(run.get("run_attempt", 1)),
                        audio="chime",
                        sender_id=str(payload.get("sender", {}).get("login", "")).lower()[:160]
                        or None,
                    )
            elif event == "deployment_status":
                self.deployment(repo, payload)
            else:
                return {"accepted": True, "ignored": True}
            with self.inbox.connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO github_deliveries VALUES (?,?)", (digest, time.time())
                )
                db.execute(
                    "DELETE FROM github_deliveries WHERE received<?", (time.time() - 30 * 86400,)
                )
        return {"accepted": True}

    def deployment(self, repo, payload):
        deployment, status = payload.get("deployment", {}), payload.get("deployment_status", {})
        state = status.get("state")
        if state not in (
            "queued",
            "pending",
            "in_progress",
            "success",
            "failure",
            "error",
            "inactive",
        ):
            raise ValueError("Invalid deployment state")
        identity = deployment.get("node_id") or str(deployment.get("id", ""))
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_=-]{1,100}", identity):
            raise ValueError("Deployment identity required")
        updated = dt.datetime.fromisoformat(status["created_at"].replace("Z", "+00:00")).timestamp()
        if updated > time.time() + 300:
            raise ValueError("Future deployment timestamp")
        name = str(deployment.get("environment") or "Deployment")[:70]
        with self.inbox.connect() as db:
            old = db.execute(
                "SELECT updated FROM github_deployments WHERE id=?", (identity,)
            ).fetchone()
            if old and old[0] >= updated:
                return
        # Publish before advancing state: a failed publish must remain retryable.
        if updated >= time.time() - 3600 and state != "inactive":
            self.publish_deployment(identity, repo, name, state)
        with self.inbox.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO github_deployments VALUES (?,?,?,?,?,?)",
                (identity, repo, name, state, updated, time.time()),
            )

    def publish_deployment(self, identity, repo, name, state):
        active = state in ("queued", "pending", "in_progress")
        failed = state in ("failure", "error")
        self.inbox.publish(
            "github",
            (
                ("Deploying · " if active else "Deploy failed · " if failed else "Deployed · ")
                + name
            )[:100],
            repo,
            "important" if failed else "normal",
            "deploy-" + identity if active else "deploy-" + identity + "-" + state,
            expires_at=time.time() + (300 if active else 3600),
            audio="chime" if failed else "silent",
        )

    def deployments(self, polled):
        with self.inbox.connect() as db:
            rows = db.execute(
                "SELECT id,repo,name,state,updated FROM github_deployments WHERE received>?",
                (time.time() - 86400,),
            ).fetchall()
        seen = {r[0] for r in rows}
        active = [
            dict(id=i, repo=r, name=n, checked=t)
            for i, r, n, s, t in rows
            if s in ("queued", "pending", "in_progress") and t > time.time() - 3600
        ]
        return active + [v for v in polled if v["id"] not in seen]

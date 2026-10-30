"""Bounded, read-only readiness probes; no observation payloads or device actions."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener
from urllib.parse import urlsplit


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


HA_HTTP = build_opener(ProxyHandler({}), NoRedirect())


def database_health(folder):
    paths = sorted(
        set(
            p
            for directory in (Path(folder), Path(folder) / "ptt", Path(folder) / "amadeus")
            for pattern in ("*.sqlite3", "*.sqlite", "*.db")
            for p in directory.glob(pattern)
        )
    )
    if not paths:
        return {"state": "waiting", "detail": "No application databases found"}
    failed = 0
    for path in paths:
        try:
            deadline = time.monotonic() + 2
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
                db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
                    failed += 1
                elif db.execute("PRAGMA foreign_key_check").fetchone():
                    failed += 1
        except sqlite3.Error:
            failed += 1
    return {
        "state": "attention" if failed else "ready",
        "detail": f"{len(paths)} databases checked; {failed} need attention",
    }


def log_findings(text):
    """Known current-run diagnostics; never expose log lines or account metadata."""
    signatures = (
        (
            "[firebase_messaging.fcmpushclient]",
            "shutting down FcmPushClient",
            "ha_push",
            "Ring push listener",
            "attention",
            "Push listener stopped during this HA run; restart or repair needed",
        ),
        (
            "[thinqconnect.integration.homeassistant.api]",
            "no profile info",
            "ha_lg_profile",
            "LG appliance profile",
            "partial",
            "A ThinQ profile could not be read; local-only devices may be unsupported",
        ),
        (
            "[ring_doorbell.stickup_cam]",
            "Unknown kind:",
            "ha_ring_model",
            "Ring model",
            "partial",
            "Unrecognized camera model; capabilities need verification",
        ),
        (
            "[homeassistant.components.recorder.util]",
            "Ended unfinished session",
            "ha_recorder",
            "HA recorder",
            "recovered",
            "Recovered an unfinished session at startup",
        ),
        (
            "[homeassistant.components.rest_command]",
            "Error fetching data",
            "ha_startup_transport",
            "HA callback history",
            "history",
            "Callback failures logged this HA run; live checks are shown separately",
        ),
    )
    lines = text.splitlines()
    return [
        {"id": key, "label": label, "state": state, "detail": detail}
        for logger, message, key, label, state, detail in signatures
        if any(logger in line and message in line for line in lines)
    ]


def home_assistant_health(folder):
    path = Path(folder) / "amadeus/amadeus.sqlite3"
    if not path.exists():
        return {"state": "not_configured", "detail": "Connect HA in Amadeus setup"}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
        row = db.execute(
            "SELECT value FROM preferences WHERE subject=? AND key=?",
            ("amadeus-system", "feed_connection.ha"),
        ).fetchone()
        cfg = json.loads(row[0]) if row else {}
    if not cfg.get("token") or not cfg.get("url"):
        return {"state": "not_configured", "detail": "Connect HA in Amadeus setup"}
    parts = urlsplit(cfg["url"])
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
    ):
        return {"state": "attention", "detail": "Review HA connection settings"}
    req = Request(
        cfg["url"].rstrip("/") + "/api/config", headers={"Authorization": "Bearer " + cfg["token"]}
    )
    with HA_HTTP.open(req, timeout=3) as response:
        value = json.loads(response.read(131072))
    ready = (
        value.get("state") == "RUNNING"
        and not value.get("safe_mode")
        and not value.get("recovery_mode")
    )
    issues = []
    try:
        request = Request(
            cfg["url"].rstrip("/") + "/api/error_log",
            headers={"Authorization": "Bearer " + cfg["token"]},
        )
        with HA_HTTP.open(request, timeout=3) as response:
            raw = response.read(1_048_577)
        issues = log_findings(raw[:1_048_576].decode("utf-8", errors="replace"))
        if len(raw) > 1_048_576:
            issues.append(
                {
                    "id": "ha_log_limit",
                    "label": "HA logs",
                    "state": "partial",
                    "detail": "Diagnostic log sample truncated",
                }
            )
    except Exception:
        issues = [
            {
                "id": "ha_log_access",
                "label": "HA logs",
                "state": "partial",
                "detail": "Log diagnostics unavailable; core probe is independent",
            }
        ]
    return {
        "issues": issues,
        "state": "ready" if ready else "waiting",
        "detail": "Core running; individual integrations may have faults"
        if ready
        else "HA core is initializing or in recovery",
    }


class Readiness:
    def __init__(
        self, folder, clock=time.time, db_probe=database_health, ha_probe=home_assistant_health
    ):
        self.folder, self.clock = folder, clock
        self.started_at = clock()
        self.db_probe, self.ha_probe = db_probe, ha_probe
        self.next_database = 0
        self.probes = {
            key: {"state": "waiting", "detail": "Checking"}
            for key in ("database", "home_assistant")
        }
        self.startup_complete_at = None
        import threading

        self.lock = threading.Lock()

    def probe(self):
        now = self.clock()
        for key, fn in (("database", self.db_probe), ("home_assistant", self.ha_probe)):
            if key == "database" and now < self.next_database:
                continue
            try:
                result = fn(self.folder)
            except Exception:
                result = {"state": "attention", "detail": "Probe unavailable; retrying"}
            self.probes[key] = {**result, "checked_at": now}
            if key == "database":
                self.next_database = now + (3600 if result["state"] == "ready" else 30)

    def snapshot(self, devices, speech, model_alive, feeds=None, github=None):
        now = self.clock()
        components = [
            {"id": key, "label": label, **self.probes[key]}
            for key, label in (("database", "Database"), ("home_assistant", "Home Assistant"))
        ]
        for key, label, healthy in (
            ("display", "Pi screen", devices.get("display", {}).get("available") is True),
            ("voice", "Pi audio", devices.get("voice", {}).get("available") is True),
            ("speech", "Voice synthesis", speech.get("available") is True),
            ("conversation", "Conversation", model_alive is True),
        ):
            components.append(
                {
                    "id": key,
                    "label": label,
                    "state": "ready" if healthy else "attention",
                    "detail": "Connected" if healthy else "Unavailable; reconnecting",
                }
            )
        core_ready = all(x["state"] in ("ready", "not_configured") for x in components)
        components.extend(self.probes["home_assistant"].get("issues", []))
        for key, health in (feeds or {}).items():
            status = health.get("state", "waiting")
            components.append(
                {
                    "id": "feed_" + key,
                    "label": key.replace("_", " ").title(),
                    "state": "ready"
                    if status == "connected"
                    else "partial"
                    if status == "connected_partial"
                    else "attention",
                    "detail": status.replace("_", " "),
                }
            )
        if github and github.get("configured"):
            pending = (
                not github.get("checked_at")
                and not github.get("auth_required")
                and github.get("error") in (None, "Connecting to AWS queue")
            )
            components.append(
                {
                    "id": "github",
                    "label": "GitHub notifications",
                    "state": "ready"
                    if github.get("available")
                    else "waiting"
                    if pending
                    else "attention",
                    "detail": "Connected"
                    if github.get("available")
                    else "Connecting"
                    if pending
                    else "Unavailable; reconnecting",
                }
            )
        with self.lock:
            first_ready = core_ready and self.startup_complete_at is None
            if first_ready:
                self.startup_complete_at = now
        if first_ready:
            print(
                "Startup complete: database, configured HA, model, speech and Pi services ready",
                flush=True,
            )
        unresolved = any(x["state"] in ("waiting", "attention") for x in components)
        state = (
            "starting"
            if unresolved
            and (
                self.startup_complete_at is None or any(c["state"] == "waiting" for c in components)
            )
            and now - self.started_at < 180
            else "attention"
            if unresolved
            else "ready"
        )
        return {
            "state": state,
            "started_at": self.started_at,
            "startup_complete_at": self.startup_complete_at,
            "checked_at": now,
            "components": components,
        }

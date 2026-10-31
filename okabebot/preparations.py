"""Private draft preparation lifecycle. No provider writes, checkout or execution."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import time
import uuid

from .amadeus import Store, encode
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY

PREFIX = "preparations.job."
STAGES = ("researching", "comparing", "drafting")
TERMINAL = ("saved", "dismissed", "canceled", "expired")
DEFAULT_MOTION = {"enabled": True, "reduced_motion": False}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def lines(items):
    if not isinstance(items, list) or not 1 <= len(items) <= 15:
        raise ValueError("Prepare a list of 1–15 items")
    output = []
    for item in items:
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= 100:
            raise ValueError("Use a short item description")
        value = " ".join(item.split())
        if value.casefold() not in [v.casefold() for v in output]:
            output.append(value)
    if len(json.dumps(output).encode()) > 2200:
        raise ValueError("Keep this draft within the bounded list size")
    return output


class Preparations:
    """High-level start/progress/ready/review API for future trusted adapters.

    Saving means retaining a local draft, never approving an external transaction.
    Future external execution needs a distinct content-bound confirmation contract.
    """

    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = Path(folder), clock

    def store(self):
        return closing(Store(self.folder, clock=self.clock))

    def prune(self):
        """Apply retention even while onboarding is paused or in guest mode."""
        with self.store() as store, store.db:
            rows = store.db.execute(
                "SELECT subject,key,value FROM preferences WHERE key LIKE ?", (PREFIX + "%",)
            ).fetchall()
            for subject, key, raw in rows:
                if self.clock() >= json.loads(raw)["expires_at"]:
                    store.db.execute(
                        "DELETE FROM preferences WHERE subject=? AND key=?", (subject, key)
                    )

    def _setup(self, store):
        setup = preference(store, SYSTEM, KEY, {})
        if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
            raise PermissionError("Private preparations require an active owner profile")
        return setup

    def _jobs(self, store, setup):
        rows = store.db.execute(
            "SELECT key,value FROM preferences WHERE subject=? AND key LIKE ?",
            (setup["profile"], PREFIX + "%"),
        ).fetchall()
        output = []
        for key, raw in rows:
            job = json.loads(raw)
            if self.clock() >= job["expires_at"]:
                store.db.execute(
                    "DELETE FROM preferences WHERE subject=? AND key=?", (setup["profile"], key)
                )
                continue
            job = self._effective(job, setup)
            output.append(job)
        return sorted(output, key=lambda j: j["created_at"], reverse=True)

    def _effective(self, job, setup):
        job = dict(job)
        if job["status"] not in TERMINAL:
            if job["consent_hash"] != digest(setup):
                job.update(status="blocked", reason="setup_changed")
            elif job["status"] == "running" and self.clock() >= job["lease_until"]:
                job.update(status="blocked", reason="worker_disconnected")
        return job

    def _write(self, store, setup, job):
        store.db.execute(
            "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (setup["profile"], PREFIX + job["id"], encode(job), self.clock()),
        )

    def start(self, kind="shopping_list", title="Shopping list", provider="local"):
        if kind not in ("shopping_list", "general") or provider not in ("local", "safeway"):
            raise ValueError("Choose a supported preparation kind/provider intent")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
            raise ValueError("Use a short draft title")
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = self._setup(store)
            jobs = self._jobs(store, setup)
            if len(jobs) >= 20:
                raise ValueError(
                    "Draft storage is full (20); temporary drafts expire after one day"
                )
            if any(j["status"] == "running" for j in jobs):
                raise ValueError("Finish or cancel running work before preparing more")
            now = self.clock()
            job = dict(
                id=uuid.uuid4().hex,
                revision=1,
                kind=kind,
                provider=provider,
                title=title.strip(),
                status="running",
                stage="researching",
                created_at=now,
                updated_at=now,
                stage_started_at=now,
                expires_at=now + 86400,
                lease_until=now + 30,
                consent_hash=digest(setup),
                items=[],
                draft_hash=None,
            )
            self._write(store, setup, job)
            return job

    def change(self, identity, revision, action, *, stage=None, items=None):
        if (
            not isinstance(identity, str)
            or len(identity) != 32
            or any(c not in "0123456789abcdef" for c in identity)
        ):
            raise ValueError("Choose a preparation")
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = self._setup(store)
            jobs = self._jobs(store, setup)
            job = next((j for j in jobs if j["id"] == identity), None)
            if not job or type(revision) is not int or revision != job["revision"]:
                raise ValueError("Draft changed or expired; refresh before reviewing")
            if action in ("cancel", "dismiss") and job["status"] not in TERMINAL:
                job["status"] = "canceled" if action == "cancel" else "dismissed"
            elif action == "progress" and job["status"] == "running" and stage in STAGES:
                if STAGES.index(stage) < STAGES.index(job["stage"]):
                    raise ValueError("Work stages cannot move backwards")
                if stage != job["stage"]:
                    job["stage_started_at"] = self.clock()
                job.update(stage=stage, lease_until=self.clock() + 30)
            elif action == "ready" and job["status"] == "running":
                value = lines(items)
                job.update(
                    status="awaiting_review",
                    stage="awaiting_review",
                    stage_started_at=self.clock(),
                    items=value,
                    draft_hash=digest(
                        {"kind": job["kind"], "provider": job["provider"], "items": value}
                    ),
                )
            elif action == "save" and job["status"] == "awaiting_review":
                job["status"] = "saved"
            else:
                raise ValueError("That preparation transition is unavailable")
            job.update(revision=job["revision"] + 1, updated_at=self.clock())
            self._write(store, setup, job)
            return job

    def motion_settings(self, data=None):
        with self.store() as store, store.db:
            if data is not None:
                if (
                    not isinstance(data, dict)
                    or set(data) != set(DEFAULT_MOTION)
                    or any(type(v) is not bool for v in data.values())
                ):
                    raise ValueError("Choose ambient animation and reduced-motion settings")
                setup = self._setup(store)
                store.remember(setup["profile"], "presentation.motion", data)
            setup = preference(store, SYSTEM, KEY, {})
            return {
                **DEFAULT_MOTION,
                **preference(store, setup.get("profile", SYSTEM), "presentation.motion", {}),
            }

    def snapshot(self):
        with self.store() as store, store.db:
            try:
                setup = self._setup(store)
            except PermissionError:
                return {
                    "jobs": [],
                    "state": "paused_or_not_configured",
                    "execution_supported": False,
                }
            jobs = [
                {k: v for k, v in j.items() if k not in ("consent_hash", "lease_until")}
                for j in self._jobs(store, setup)
            ]
            return {
                "jobs": jobs,
                "execution_supported": False,
                "scope": "Local drafts only; nothing is added to a retailer account or ordered.",
            }

    def presentation(self):
        with self.store() as store, store.db:
            try:
                setup = self._setup(store)
            except PermissionError:
                return {}
            jobs = self._jobs(store, setup)
            job = next(
                (j for j in jobs if j["status"] in ("running", "awaiting_review", "blocked")), None
            )
            if not job:
                return {}
            # No title, list contents, provider, account, identity or household data.
            return {
                "kind": job["kind"],
                "stage": job["stage"] if job["status"] == "running" else job["status"],
                "elapsed_seconds": max(0, self.clock() - job["stage_started_at"]),
                "lease_seconds": 8,
            }

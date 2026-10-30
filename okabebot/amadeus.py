"""Offline Amadeus event/preference foundation. No collectors, inference or actions."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid


FIELDS = {
    "feed_snapshot": {"provider", "items", "complete", "valid_until_at"},
    "presence": {"state", "room"},
    "door": {"state"},
    "household_event": {"provider", "event", "detail", "provenance"},
    "interaction": {"action", "surface"},
    "media": {"app", "title", "content_id", "state", "duration_s", "position_s", "device_id"},
    "calendar": {"event_id", "summary", "start_at", "end_at", "snapshot_id", "busy", "all_day"},
    "calendar_snapshot": {"snapshot_id", "event_count", "start_at", "end_at", "busy_coverage"},
    "availability": {"signal", "state", "device_id", "observation"},
    "tv_state": {"state", "device_id", "observation"},
    "phone_wake": {"state"},
    "phone_alarm": {"alarm_at"},
    "weather": {"condition", "temperature_c", "reported_at"},
    "morning_summary": {"day", "target", "until_at"},
    "feedback": {"proposal_id", "outcome"},
}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", value):
        raise ValueError("Use a lowercase identifier, at most 80 characters")
    return value


def encode(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > 4096:
        raise ValueError("Structured value exceeds 4096 bytes")
    return raw


class Store:
    """Private, subject-scoped local records; source names are not authentication.

    Only explicit offline input is supported. Future collectors must enforce
    authenticated source/subject bindings outside this store. No derived memories
    exist yet; explicit preferences have independent user-stated provenance.
    """

    def __init__(self, folder, *, sources=(), retention_days=30, clock=time.time):
        if type(retention_days) is not int or not 1 <= retention_days <= 365:
            raise ValueError("Retention must be 1–365 days")
        self.sources = frozenset(identifier(s) for s in sources)
        self.clock, self.retention = clock, retention_days * 86400
        folder = Path(folder).absolute()
        if folder.is_symlink():
            raise PermissionError("Use a private non-symlink directory")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = folder.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError("Amadeus directory must be owned and private (0700)")
        path = folder / "amadeus.sqlite3"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise PermissionError("Amadeus database must be an owned private regular file")
        else:
            os.close(fd)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise ValueError("Unsupported Amadeus schema version")
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL,
                    subject TEXT NOT NULL, kind TEXT NOT NULL, observed_at REAL NOT NULL,
                    expires_at REAL NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(source, external_id));
                CREATE INDEX IF NOT EXISTS event_subject_time ON events(subject, observed_at);
                CREATE INDEX IF NOT EXISTS event_kind_time ON events(kind, subject, observed_at);
                CREATE TABLE IF NOT EXISTS preferences (
                    subject TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
                    updated_at REAL NOT NULL, PRIMARY KEY(subject, key));
                PRAGMA user_version=1;
            """)
        self.prune()

    def close(self):
        self.db.close()

    def observe(self, *, source, external_id, subject, kind, payload, observed_at=None):
        if source not in self.sources:
            raise PermissionError("Observation source is not allowlisted")
        identifier(subject)
        if not isinstance(external_id, str) or not 1 <= len(external_id) <= 128:
            raise ValueError("Provide a bounded stable source event ID")
        if kind not in FIELDS or not isinstance(payload, dict) or not payload:
            raise ValueError("Provide a supported event kind and structured payload")
        if set(payload) - FIELDS[kind]:
            raise ValueError("Unsupported event fields; raw bodies/audio are not accepted")
        if kind == "feed_snapshot":
            from .adapters.context import validate_snapshot

            validate_snapshot(payload)
        for key, value in payload.items():
            if kind == "feed_snapshot" and key == "items":
                continue
            if key.endswith("_s") or key.endswith("_at") or key in ("event_count", "temperature_c"):
                if key == "temperature_c":
                    if (
                        type(value) not in (int, float)
                        or not math.isfinite(value)
                        or not -100 <= value <= 100
                    ):
                        raise ValueError("Use a supported weather temperature")
                    continue
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("Event measurements must be finite nonnegative numbers")
            elif not isinstance(value, str) or not 1 <= len(value) <= 512:
                raise ValueError("Event text fields must contain 1–512 characters")
        if kind == "presence" and payload.get("state") not in ("home", "away", "unknown"):
            raise ValueError("Presence requires home, away or unknown")
        if kind == "door" and payload.get("state") not in ("open", "closed", "unknown"):
            raise ValueError("Door requires open, closed or unknown")
        raw, now = encode(payload), self.clock()
        supplied_time = observed_at is not None
        observed_at = now if observed_at is None else observed_at
        if type(observed_at) not in (float, int) or not math.isfinite(observed_at):
            raise ValueError("Use a finite observation timestamp")
        if observed_at < 0 or observed_at > now + 300:
            raise ValueError("Observation timestamp is invalid or too far in the future")
        expiry = observed_at + self.retention
        if expiry <= now:
            return {"status": "expired"}
        event_id = uuid.uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)",
                (event_id, source, external_id, subject, kind, observed_at, expiry, raw),
            )
            row = self.db.execute(
                "SELECT * FROM events WHERE source=? AND external_id=?", (source, external_id)
            ).fetchone()
            expected = (subject, kind, observed_at if supplied_time else row["observed_at"], raw)
            if tuple(row[k] for k in ("subject", "kind", "observed_at", "payload")) != expected:
                raise ValueError("Source event ID was reused with conflicting contents")
        return {"status": "stored" if row["id"] == event_id else "duplicate", "id": row["id"]}

    def remember(self, subject, key, value):
        subject, key = identifier(subject), identifier(key)
        with self.db:
            self.db.execute(
                "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) "
                "DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (subject, key, encode(value), self.clock()),
            )

    def recall(self, subject, *, limit=20):
        identifier(subject)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Recall limit must be 1–100")
        events = self.db.execute(
            "SELECT * FROM events WHERE subject=? AND expires_at>? "
            "ORDER BY observed_at DESC, id LIMIT ?",
            (subject, self.clock(), limit),
        ).fetchall()
        prefs = self.db.execute(
            "SELECT key,value,updated_at FROM preferences WHERE subject=? ORDER BY key", (subject,)
        ).fetchall()
        return {
            "events": [dict(row, payload=json.loads(row["payload"])) for row in events],
            "preferences": [
                dict(row, value=json.loads(row["value"]), provenance="explicit") for row in prefs
            ],
        }

    def forget(self, subject, *, key=None):
        identifier(subject)
        with self.db:
            if key is not None:
                identifier(key)
                return self.db.execute(
                    "DELETE FROM preferences WHERE subject=? AND key=?", (subject, key)
                ).rowcount
            from .context_records import clear

            clear(self.db, subject=subject)
            count = self.db.execute("DELETE FROM preferences WHERE subject=?", (subject,)).rowcount
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='context_exposures'"
            ).fetchone():
                count += self.db.execute(
                    "DELETE FROM context_exposures WHERE subject=?", (subject,)
                ).rowcount
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shadow_decisions'"
            ).fetchone():
                self.db.execute(
                    "DELETE FROM shadow_decisions WHERE evaluated_at<=?",
                    (self.clock() - min(self.retention, 7 * 86400),),
                )
            return (
                count + self.db.execute("DELETE FROM events WHERE subject=?", (subject,)).rowcount
            )

    def prune(self):
        from .context_records import prune

        prune(self.db, self.clock())
        with self.db:
            count = 0
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='context_exposures'"
            ).fetchone():
                count = self.db.execute(
                    "DELETE FROM context_exposures WHERE shown_at<=?",
                    (self.clock() - min(self.retention, 7 * 86400),),
                ).rowcount
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shadow_decisions'"
            ).fetchone():
                self.db.execute(
                    "DELETE FROM shadow_decisions WHERE evaluated_at<=?",
                    (self.clock() - min(self.retention, 7 * 86400),),
                )
            return (
                count
                + self.db.execute(
                    "DELETE FROM events WHERE expires_at<=?", (self.clock(),)
                ).rowcount
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--folder", type=Path, required=True, help="Private offline state directory"
    )
    parser.add_argument("--allow-source", action="append", default=[])
    commands = parser.add_subparsers(dest="command", required=True)
    event = commands.add_parser("observe")
    for field in ("source", "external-id", "subject", "kind", "payload"):
        event.add_argument("--" + field, required=True)
    event.add_argument("--observed-at", type=float)
    preference = commands.add_parser("remember")
    for field in ("subject", "key", "value"):
        preference.add_argument("--" + field, required=True)
    recall = commands.add_parser("recall")
    recall.add_argument("--subject", required=True)
    forget = commands.add_parser("forget")
    forget.add_argument("--subject", required=True)
    forget.add_argument("--key")
    commands.add_parser("prune")
    args = parser.parse_args()
    store = Store(args.folder, sources=args.allow_source)
    try:
        if args.command == "observe":
            result = store.observe(
                source=args.source,
                external_id=args.external_id,
                subject=args.subject,
                kind=args.kind,
                payload=json.loads(args.payload),
                observed_at=args.observed_at,
            )
        elif args.command == "remember":
            store.remember(args.subject, args.key, json.loads(args.value))
            result = {"status": "remembered", "provenance": "explicit"}
        elif args.command == "recall":
            result = store.recall(args.subject)
        elif args.command == "forget":
            result = {"deleted": store.forget(args.subject, key=args.key)}
        else:
            result = {"deleted": store.prune()}
        print(json.dumps(result, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()

"""Durable, deduplicated notifications. No LLM or arbitrary tool execution."""

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

PRIORITIES = {"low": 0, "normal": 1, "important": 2, "urgent": 3}


class Inbox:
    def __init__(self, folder, group_window_seconds=3):
        self.group_window = float(group_window_seconds)
        if not 0 <= self.group_window <= 10:
            raise ValueError("Grouping window must be 0..10 seconds")
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.path = Path(folder) / "notifications.sqlite3"
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, dedupe TEXT UNIQUE, payload TEXT, created REAL, due REAL, expires REAL, priority INTEGER, status TEXT, error TEXT)"
            )

            columns = {r[1] for r in db.execute("PRAGMA table_info(notifications)")}
            for name in ("group_key", "batch_id"):
                if name not in columns:
                    db.execute("ALTER TABLE notifications ADD COLUMN " + name + " TEXT")
            db.execute(
                "CREATE INDEX IF NOT EXISTS notification_groups ON notifications(group_key,status,due)"
            )

    def recover(self):
        with self.connect() as db:
            db.execute(
                "UPDATE notifications SET status='uncertain', error='Controller restarted during delivery' WHERE status='delivering'"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def publish(
        self,
        source,
        title,
        body="",
        priority="normal",
        dedupe_key=None,
        due_at=None,
        expires_at=None,
        audio="default",
        group_key=None,
        group_title=None,
        sender_id=None,
        sender_label=None,
    ):
        for value, limit in ((sender_id, 160), (sender_label, 80)):
            if value is not None and (
                not isinstance(value, str)
                or not 1 <= len(value) <= limit
                or value != value.strip()
                or any(ord(c) < 32 for c in value)
            ):
                raise ValueError("Invalid literal sender metadata")
        if sender_label is not None and sender_id is None:
            raise ValueError("Sender label requires a stable sender_id")
        now = time.time()
        if group_key is not None and (
            not isinstance(group_key, str) or not 1 <= len(group_key) <= 100
        ):
            raise ValueError("Invalid notification group")
        if group_title is not None and (
            not isinstance(group_title, str) or not 1 <= len(group_title.strip()) <= 80
        ):
            raise ValueError("Invalid group title")
        if audio not in ("default", "silent", "chime"):
            raise ValueError("Unknown notification audio policy")
        if (
            not isinstance(source, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,29}", source)
            or priority not in PRIORITIES
        ):
            raise ValueError("Unknown source or priority")
        for value, limit in ((title, 100), (body, 500)):
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError("Notification text is too long")
        if not title.strip():
            raise ValueError("A title is required")
        due = now if due_at is None else float(due_at)
        expires = due + 3600 if expires_at is None else float(expires_at)
        import math

        if not math.isfinite(due) or not math.isfinite(expires) or expires <= due:
            raise ValueError("Invalid notification dates")
        key = dedupe_key or uuid.uuid4().hex
        if not isinstance(key, str) or not 1 <= len(key) <= 300:
            raise ValueError("Invalid deduplication key")
        identifier = uuid.uuid4().hex
        payload = dict(id=identifier, source=source, title=title, body=body, priority=priority)
        payload["audio"] = audio
        if sender_id is not None:
            payload.update(sender_id=sender_id, sender_label=sender_label or sender_id)
            from .notification_policy import NotificationPolicy

            priority = NotificationPolicy(self.path.parent).priority(payload)
            payload["priority"] = priority
            if group_key:
                import hashlib

                group_key += ":sender-" + hashlib.sha256(sender_id.encode()).hexdigest()[:16]
        if group_key:
            payload.update(group_key=group_key, group_title=group_title or "Related activity")
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO notifications (id,dedupe,payload,created,due,expires,priority,status,error,group_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    source + ":" + key,
                    json.dumps(payload),
                    now,
                    due,
                    expires,
                    PRIORITIES[priority],
                    "pending",
                    None,
                    source + ":" + group_key if group_key and priority != "urgent" else None,
                ),
            )
            row = db.execute(
                "SELECT payload FROM notifications WHERE dedupe=?", (source + ":" + key,)
            ).fetchone()
        return json.loads(row[0])

    def claim(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE notifications SET status='expired' WHERE status='pending' AND expires<=?",
                (now,),
            )
            pending = db.execute(
                "SELECT id,payload,group_key FROM notifications WHERE status='pending' AND due<=? ORDER BY priority DESC,due ASC LIMIT 100",
                (now,),
            ).fetchall()
            visited = set()
            for identifier, raw, group in pending:
                item = json.loads(raw)
                members = [(identifier, raw)]
                if group and self.group_window:
                    if group in visited:
                        continue
                    visited.add(group)
                    rows = db.execute(
                        "SELECT id,payload,due FROM notifications WHERE status='pending' AND group_key=? AND due<=? ORDER BY due ASC",
                        (group, now),
                    ).fetchall()
                    cutoff = rows[0][2] + self.group_window
                    if now < cutoff:
                        continue
                    members = [(i, p) for i, p, due in rows if due <= cutoff]
                    identifier = members[0][0]
                    item = json.loads(members[0][1])
                ids = [i for i, _ in members]
                db.executemany(
                    "UPDATE notifications SET status='delivering',batch_id=? WHERE id=?",
                    [(identifier, i) for i in ids],
                )
                if len(members) > 1:
                    values = [json.loads(p) for _, p in members]
                    titles = list(dict.fromkeys(v["title"] for v in values))
                    item = dict(
                        item,
                        title=(
                            item.get("group_title", "Related activity") + " (" + str(len(ids)) + ")"
                        )[:100],
                        body=" · ".join(titles[:3])[:500],
                        priority=max(values, key=lambda v: PRIORITIES[v["priority"]])["priority"],
                        # Never turn a silent constituent into spoken content.
                        audio="silent"
                        if any(v.get("audio") == "silent" for v in values)
                        else item.get("audio", "default"),
                        member_ids=ids,
                    )
                return item
            return None

    def finish(self, identifier, error=None):
        with self.connect() as db:
            db.execute(
                "UPDATE notifications SET status=?,error=? WHERE id=? OR batch_id=?",
                ("failed" if error else "delivered", error, identifier, identifier),
            )

    def dismiss(self, identifier):
        with self.connect() as db:
            db.execute(
                "UPDATE notifications SET status='dismissed' WHERE id=? OR batch_id=(SELECT batch_id FROM notifications WHERE id=?)",
                (identifier, identifier),
            )

    def suppress(self, identifier):
        with self.connect() as db:
            db.execute(
                "UPDATE notifications SET status='suppressed' WHERE id=? OR batch_id=?",
                (identifier, identifier),
            )

    def items(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload,status,error,due FROM notifications ORDER BY created DESC LIMIT 30"
            ).fetchall()
        return [dict(json.loads(p), status=s, error=e, due_at=d) for p, s, e, d in rows]

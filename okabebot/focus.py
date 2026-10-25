"""Focus timer stored in the existing durable notification queue."""

import json
import time
import uuid


class FocusTimer:
    def __init__(self, inbox):
        self.inbox = inbox

    def status(self):
        with self.inbox.connect() as db:
            row = db.execute(
                "SELECT id,due FROM notifications WHERE dedupe LIKE 'system:focus-%' AND status='pending' ORDER BY created DESC LIMIT 1"
            ).fetchone()
        return {
            "active": bool(row),
            "ends_at": row[1] if row else None,
            "id": row[0] if row else None,
        }

    def cancel(self):
        with self.inbox.connect() as db:
            db.execute(
                "UPDATE notifications SET status='cancelled' WHERE dedupe LIKE 'system:focus-%' AND status='pending'"
            )

    def start(self, minutes):
        if type(minutes) is not int or not 1 <= minutes <= 180:
            raise ValueError("Choose 1–180 minutes")
        now = time.time()
        identifier = uuid.uuid4().hex
        payload = dict(
            id=identifier,
            source="system",
            title="Focus session finished",
            body="Time for a break. You focused for %s minutes." % minutes,
            priority="important",
        )
        with self.inbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE notifications SET status='cancelled' WHERE dedupe LIKE 'system:focus-%' AND status='pending'"
            )
            db.execute(
                "INSERT INTO notifications (id,dedupe,payload,created,due,expires,priority,status,error) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    "system:focus-" + identifier,
                    json.dumps(payload),
                    now,
                    now + minutes * 60,
                    now + minutes * 60 + 900,
                    2,
                    "pending",
                    None,
                ),
            )
        return self.status()

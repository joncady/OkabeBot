"""Personal reminders in the shared durable notification inbox."""

import re
import time


class Reminders:
    def __init__(self, inbox):
        self.inbox = inbox

    def create(self, text, minutes, request_id, audio="chime"):
        if type(minutes) is not int or not 1 <= minutes <= 525600:
            raise ValueError("minutes must be 1–525600")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise ValueError("Use a unique request_id of 8–100 letters/digits/-/_")
        if audio not in ("silent", "chime", "default"):
            raise ValueError("Invalid audio policy")
        due = time.time() + minutes * 60
        item = self.inbox.publish(
            "reminder",
            "Reminder",
            text,
            "important",
            "personal-" + request_id,
            due,
            due + 86400,
            audio=audio,
        )

        with self.inbox.connect() as db:
            row = db.execute(
                "SELECT due,status FROM notifications WHERE id=?", (item["id"],)
            ).fetchone()
        return dict(item, due_at=row[0], status=row[1])

    def list(self):
        import json

        with self.inbox.connect() as db:
            rows = db.execute(
                "SELECT payload,due FROM notifications WHERE dedupe LIKE 'reminder:personal-%' AND status='pending' ORDER BY due LIMIT 100"
            ).fetchall()
        return [dict(json.loads(payload), due_at=due) for payload, due in rows]

    def cancel(self, identifier):
        with self.inbox.connect() as db:
            result = db.execute(
                "UPDATE notifications SET status='cancelled' WHERE id=? AND dedupe LIKE 'reminder:personal-%' AND status='pending'",
                (identifier,),
            )
        return {"cancelled": bool(result.rowcount), "id": identifier}

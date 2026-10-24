import json
import re
import sqlite3
import threading
import time


class PressController:
    def __init__(self, database, bot):
        self.database, self.bot = str(database), bot
        self.lock = threading.Lock()
        with sqlite3.connect(self.database) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS presses (id TEXT PRIMARY KEY, result TEXT, created REAL)"
            )

    def press(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise ValueError("request_id must be 8–100 letters, digits, underscores or hyphens")
        with self.lock, sqlite3.connect(self.database) as db:
            old = db.execute("SELECT result FROM presses WHERE id=?", (request_id,)).fetchone()
            if old:
                return dict(json.loads(old[0]), deduplicated=True)
            last = db.execute("SELECT MAX(created) FROM presses").fetchone()[0]
            if last and time.time() - last < 3:
                return {"outcome": "not_sent", "error": "Wait three seconds between presses"}
            pending = {
                "request_id": request_id,
                "outcome": "unknown",
                "error": "Request was recorded; completion was not confirmed. Do not retry with a new ID.",
            }
            db.execute(
                "INSERT INTO presses VALUES (?, ?, ?)",
                (request_id, json.dumps(pending), time.time()),
            )
            db.commit()  # persist before actuation, including across power failures
            try:
                result = dict(self.bot.command("570100"), request_id=request_id)
            except Exception:
                result = pending
            db.execute("UPDATE presses SET result=? WHERE id=?", (json.dumps(result), request_id))
            db.commit()
            return result

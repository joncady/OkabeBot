"""One bounded, expiring, single-use audio upload; no playback or file access."""

import threading
import time
import uuid


class PreparedAudio:
    def __init__(self, validate, clock=time.monotonic):
        self.validate, self.clock = validate, clock
        self.lock = threading.Lock()
        self.item = None

    def prepare(self, raw):
        duration = self.validate(raw)
        token = uuid.uuid4().hex
        with self.lock:
            self.item = (token, raw, self.clock() + 60)
        return {"prepared_id": token, "duration_seconds": duration}

    def take(self, token):
        with self.lock:
            item = self.item
            if item is None or item[0] != token or self.clock() >= item[2]:
                raise ValueError("Prepared audio is missing or expired")
            self.item = None
            return item[1]

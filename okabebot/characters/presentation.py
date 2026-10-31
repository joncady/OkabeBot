"""Content-retaining notification entrance/exit; independent of facial clocks."""

import json
import time


def ease(value):
    value = min(1, max(0, value))
    return value * value * (3 - 2 * value)


class Notice:
    """Latest pending content replaces the visible card only after it leaves."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.last = clock()
        self.current = None
        self.desired = None
        self.progress = 0
        self.current_key = self.desired_key = self.key(None)

    @staticmethod
    def key(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def set(self, value, now=None):
        now = self.clock() if now is None else now
        self.sample(now)
        self.desired_key = self.key(value)
        self.desired = json.loads(self.desired_key)
        if value is None and self.current is not None:
            # Withdrawal may be a privacy gate: remove text immediately, animate geometry only.
            self.current = {"title": "", "body": "", "source": ""}
            self.current_key = self.key(self.current)
        if self.current is None and value is not None:
            self.current = self.desired
            self.current_key = self.desired_key
            self.progress = 0
        self.last = now

    def sample(self, now=None, reduced=False):
        now = self.clock() if now is None else now
        elapsed = max(0, now - self.last)
        self.last = now
        if reduced:
            self.current = self.desired
            self.current_key = self.desired_key
            self.progress = 1 if self.current is not None else 0
        elif self.current is not None:
            opening = self.current_key == self.desired_key
            self.progress = (
                min(1, self.progress + elapsed / 0.5)
                if opening
                else max(0, self.progress - elapsed / 0.3)
            )
            if not opening and self.progress == 0:
                self.current = self.desired
                self.current_key = self.desired_key
        return self.current, ease(self.progress)

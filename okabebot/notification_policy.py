"""Persistent delivery preferences, separate from provider event content."""

from copy import deepcopy
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from zoneinfo import ZoneInfo

DEFAULTS = {
    "quiet_hours": {"enabled": False, "start": "22:00", "end": "08:00", "timezone": "local"},
    "snoozed_until": 0,
    "sources": {},
}


class NotificationPolicy:
    def __init__(self, folder, speak_important=True):
        self.path = Path(folder) / "notification-policy.json"
        self.lock = threading.RLock()
        self.speak_important = speak_important
        self.settings = deepcopy(DEFAULTS)
        if self.path.exists():
            self.settings = self.validate(json.loads(self.path.read_text()))

    @staticmethod
    def validate(value):
        if not isinstance(value, dict) or set(value) != set(DEFAULTS):
            raise ValueError("Invalid notification preferences")
        q = value["quiet_hours"]
        if not isinstance(q, dict) or set(q) != set(DEFAULTS["quiet_hours"]):
            raise ValueError("Invalid quiet hours")
        if type(q["enabled"]) is not bool:
            raise ValueError("Quiet hours enabled must be boolean")
        for field in ("start", "end"):
            if not isinstance(q[field], str) or not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", q[field]
            ):
                raise ValueError("Quiet hours use HH:MM")
        if q["start"] == q["end"]:
            raise ValueError("Quiet hours start and end must differ")
        if not isinstance(q["timezone"], str):
            raise ValueError("Timezone must be local or an IANA timezone")
        if q["timezone"] != "local":
            try:
                ZoneInfo(q["timezone"])
            except (KeyError, ValueError):
                raise ValueError("Unknown timezone") from None
        until = value["snoozed_until"]
        if type(until) not in (int, float) or not math.isfinite(until) or until < 0:
            raise ValueError("Invalid snooze time")
        if not isinstance(value["sources"], dict) or len(value["sources"]) > 100:
            raise ValueError("Invalid source rules")
        for source, rule in value["sources"].items():
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,29}", source):
                raise ValueError("Invalid notification source")
            if (
                not isinstance(rule, dict)
                or set(rule) != {"enabled", "audio"}
                or type(rule["enabled"]) is not bool
                or rule["audio"] not in ("default", "silent", "chime", "speech")
            ):
                raise ValueError("Source rules need enabled and audio")
        return deepcopy(value)

    def update(self, changes):
        with self.lock:
            if not isinstance(changes, dict) or set(changes) - set(DEFAULTS):
                raise ValueError("Unknown notification preference")
            candidate = deepcopy(self.settings)
            for key, value in changes.items():
                if key in ("quiet_hours", "sources") and isinstance(value, dict):
                    candidate[key].update(value)
                else:
                    candidate[key] = value
            candidate = self.validate(candidate)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as f:
                json.dump(candidate, f)
                temporary = Path(f.name)
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)
            self.settings = candidate
            return self.snapshot()

    def quiet(self, now=None):
        q = self.settings["quiet_hours"]
        if not q["enabled"]:
            return False
        date = dt.datetime.fromtimestamp(time.time() if now is None else now, dt.timezone.utc)
        date = date.astimezone(None if q["timezone"] == "local" else ZoneInfo(q["timezone"]))
        clock = date.strftime("%H:%M")
        return (
            q["start"] <= clock < q["end"]
            if q["start"] < q["end"]
            else clock >= q["start"] or clock < q["end"]
        )

    def snapshot(self):
        with self.lock:
            return dict(
                deepcopy(self.settings),
                quiet_active=self.quiet(),
                snoozed=self.settings["snoozed_until"] > time.time(),
            )

    def enabled(self, source):
        return self.settings["sources"].get(source, {}).get("enabled", True)

    def audio(self, item, now=None):
        mode = self.settings["sources"].get(item["source"], {}).get("audio", "default")
        explicit = item.get("audio", "default")
        if self.quiet(now) or explicit == "silent" or mode == "silent":
            return "silent"
        if explicit == "chime":
            return "chime"
        if mode != "default":
            return mode
        return (
            "speech"
            if self.speak_important and item["priority"] in ("important", "urgent")
            else "silent"
        )

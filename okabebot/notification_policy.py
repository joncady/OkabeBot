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
    "senders": [],
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
        if isinstance(value, dict) and "senders" not in value:
            value = dict(value, senders=[])  # Backward-compatible preference migration.
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
        rules = value["senders"]
        if not isinstance(rules, list) or len(rules) > 100:
            raise ValueError("Choose at most 100 literal sender rules")
        seen = set()
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) != {
                "source",
                "sender_id",
                "enabled",
                "audio",
                "priority",
            }:
                raise ValueError("Invalid sender rule fields")
            if not isinstance(rule["source"], str) or not re.fullmatch(
                r"[a-z][a-z0-9_-]{0,29}", rule["source"]
            ):
                raise ValueError("Invalid sender source")
            identity = rule["sender_id"]
            if (
                not isinstance(identity, str)
                or not 1 <= len(identity) <= 160
                or identity != identity.strip()
                or any(ord(c) < 32 for c in identity)
            ):
                raise ValueError("Sender identity must be literal text, 1–160 characters")
            if (
                type(rule["enabled"]) is not bool
                or rule["audio"] not in ("default", "silent", "chime", "speech")
                or rule["priority"] not in ("default", "low", "normal", "important", "urgent")
            ):
                raise ValueError("Invalid sender delivery preference")
            key = (rule["source"], identity)
            if key in seen:
                raise ValueError("Duplicate sender rule")
            seen.add(key)
        return deepcopy(value)

    def update(self, changes):
        with self.lock:
            if not isinstance(changes, dict) or set(changes) - set(DEFAULTS):
                raise ValueError("Unknown notification preference")
            candidate = deepcopy(self.settings)
            for key, value in changes.items():
                if key == "sources" and isinstance(value, dict):
                    for source, rule in value.items():
                        if not isinstance(rule, dict):
                            raise ValueError("Source changes must be field patches")
                        current = candidate["sources"].get(
                            source, {"enabled": True, "audio": "default"}
                        )
                        candidate["sources"][source] = {**current, **rule}
                elif key == "quiet_hours" and isinstance(value, dict):
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

    def sender_rule(self, item):
        with self.lock:
            return next(
                (
                    dict(r)
                    for r in self.settings["senders"]
                    if r["source"] == item["source"] and r["sender_id"] == item.get("sender_id")
                ),
                {},
            )

    def enabled_item(self, item):
        return self.enabled(item["source"]) and self.sender_rule(item).get("enabled", True)

    def priority(self, item):
        value = self.sender_rule(item).get("priority", "default")
        return item["priority"] if value == "default" else value

    def set_sender(self, source, sender_id, enabled=None, audio=None, priority=None):
        with self.lock:
            current = self.sender_rule({"source": source, "sender_id": sender_id})
            rule = {
                "source": source,
                "sender_id": sender_id,
                "enabled": current.get("enabled", True) if enabled is None else enabled,
                "audio": current.get("audio", "default") if audio is None else audio,
                "priority": current.get("priority", "default") if priority is None else priority,
            }
            rules = [
                r
                for r in self.settings["senders"]
                if (r["source"], r["sender_id"]) != (source, sender_id)
            ]
            return self.update({"senders": rules + [rule]})

    def delete_sender(self, source, sender_id):
        with self.lock:
            return self.update(
                {
                    "senders": [
                        r
                        for r in self.settings["senders"]
                        if (r["source"], r["sender_id"]) != (source, sender_id)
                    ]
                }
            )

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
        sender = self.sender_rule(item).get("audio", "default")
        if self.quiet(now) or explicit == "silent" or mode == "silent" or sender == "silent":
            return "silent"
        if explicit == "chime":
            return "chime"
        if sender != "default":
            return sender
        if mode != "default":
            return mode
        return (
            "speech"
            if self.speak_important and item["priority"] in ("important", "urgent")
            else "silent"
        )

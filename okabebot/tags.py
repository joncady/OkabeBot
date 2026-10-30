"""Private tag mappings: short-lived learning and explicitly bound actions only."""

import re
import threading
import time
from pathlib import Path
from .presence_control import read, write


def tag_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_:.-]{1,128}", value):
        raise ValueError("Use a tag ID from a Home Assistant scan")
    return value


class Tags:
    def __init__(self, folder, locations, call, clock=time.time):
        self.folder, self.locations, self.call, self.clock = Path(folder), locations, call, clock
        self.lock = threading.RLock()
        self.learn_until = 0
        self.learned = None

    def snapshot(self):
        with self.lock:
            state = read(self.folder / "state.json", {})
            return {
                "mappings": list(read(self.folder / "mappings.json", {}).values()),
                "locations": [
                    {"id": p["id"], "name": p["name"]}
                    for p in self.locations()
                    if p.get("approved")
                ],
                "learning": self.clock() < self.learn_until,
                "learned": self.learned if self.clock() < self.learn_until else None,
                "last_scan": state.get("last_scan"),
            }

    def learn(self):
        with self.lock:
            self.learn_until, self.learned = self.clock() + 90, None
            return self.snapshot()

    def save(self, data):
        if not isinstance(data, dict) or set(data) != {"tag_id", "name", "location_id", "enabled"}:
            raise ValueError("Choose tag, name, destination and enabled state")
        key = tag_id(data["tag_id"])
        if not isinstance(data["name"], str) or not 1 <= len(data["name"].strip()) <= 80:
            raise ValueError("Use a name of 1–80 characters")
        if type(data["enabled"]) is not bool:
            raise ValueError("Choose enabled or disabled")
        if data["location_id"] not in {p["id"] for p in self.locations() if p.get("approved")}:
            raise ValueError("Choose an approved destination")
        with self.lock:
            mappings = read(self.folder / "mappings.json", {})
            if len(mappings) >= 100 and key not in mappings:
                raise ValueError("At most 100 mapped tags")
            mappings[key] = {**data, "name": data["name"].strip(), "action": "call_companion"}
            write(self.folder / "mappings.json", mappings)
            self.learn_until = 0
            return self.snapshot()

    def remove(self, key):
        key = tag_id(key)
        with self.lock:
            mappings = read(self.folder / "mappings.json", {})
            mappings.pop(key, None)
            write(self.folder / "mappings.json", mappings)
            return self.snapshot()

    def dispatch(self, key):
        mapping = read(self.folder / "mappings.json", {}).get(tag_id(key))
        if not mapping or not mapping["enabled"]:
            return {"status": "unmapped_or_disabled"}
        if mapping["location_id"] not in {p["id"] for p in self.locations() if p.get("approved")}:
            return {"status": "destination_unavailable"}
        try:
            result = self.call(mapping["location_id"])
            if result.get("error") or result.get("accepted") is False:
                return {"status": "failed; check destination"}
            return {"status": "request_sent", "location_id": mapping["location_id"]}
        except Exception:
            return {"status": "failed; check destination before retrying"}

    def scan(self, data):
        if not isinstance(data, dict) or set(data) != {"tag_id", "event_id", "observed_at"}:
            raise ValueError("Invalid tag scan")
        key = tag_id(data["tag_id"])
        event = tag_id(data["event_id"])
        now = self.clock()
        if (
            type(data["observed_at"]) not in (int, float)
            or not 0 <= now - data["observed_at"] <= 60
        ):
            raise ValueError("Stale tag scan")
        with self.lock:
            state = read(self.folder / "state.json", {})
            seen = {k: v for k, v in state.get("seen", {}).items() if 0 <= now - v <= 120}
            if event in seen:
                return {"status": "duplicate"}
            seen[event] = now
            state["seen"] = dict(list(seen.items())[-64:])
            last = state.get("last_scan") or {}
            if now < self.learn_until:
                self.learned = key
                result = {"status": "registered_for_review"}
            elif last.get("tag_id") == key and 0 <= now - last.get("at", 0) < 3:
                result = {"status": "debounced"}
            else:
                result = None
            # Persist consumption before any physical action. Never auto-retry.
            state["last_scan"] = {
                "tag_id": key,
                "at": now,
                "status": (result or {}).get("status", "processing"),
            }
            write(self.folder / "state.json", state)
            if result is None:
                result = self.dispatch(key)
            state["last_scan"]["status"] = result["status"]
            write(self.folder / "state.json", state)
            return result

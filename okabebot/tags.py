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
    def __init__(
        self,
        folder,
        locations,
        call,
        clock=time.time,
        chores=None,
        areas=None,
        room_follow=None,
        kitchen=None,
    ):
        self.folder, self.locations, self.call, self.clock = Path(folder), locations, call, clock
        self.chores = chores
        self.kitchen = kitchen
        self.room_follow = room_follow
        self.areas = areas or (lambda: {"state": "not_connected", "tags": {}})
        self.lock = threading.RLock()
        self.learn_until = 0
        self.learned = None

    def snapshot(self):
        with self.lock:
            state = read(self.folder / "state.json", {})
            areas = self.areas()
            mappings = []
            for mapping in read(self.folder / "mappings.json", {}).values():
                area = areas.get("tags", {}).get(mapping["tag_id"])
                mappings.append(
                    {
                        **mapping,
                        "ha_area": area,
                        "area_status": ("assigned" if area.get("area_id") else "unassigned")
                        if area is not None
                        else "missing"
                        if areas["state"] == "ready"
                        else areas["state"],
                    }
                )
            return {
                "mappings": mappings,
                "tag_areas": areas.get("tags", {}),
                "locations": [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "area_id": p.get("area_id"),
                        "area_name": p.get("area_name"),
                        "floor_name": p.get("floor_name"),
                    }
                    for p in self.locations()
                    if p.get("approved")
                ],
                "learning": self.clock() < self.learn_until,
                "learned": self.learned if self.clock() < self.learn_until else None,
                "last_scan": state.get("last_scan"),
                "room_cue": self.room_follow.cue() if self.room_follow else None,
            }

    def learn(self):
        with self.lock:
            self.learn_until, self.learned = self.clock() + 90, None
            return self.snapshot()

    def save(self, data):
        if not isinstance(data, dict):
            raise ValueError("Choose a tag action")
        action = data.get("action", "call_companion")
        kitchen_action = action in ("kitchen_used_up", "kitchen_reorder")
        expected = {"tag_id", "name", "enabled"} | (
            {"product_id", "quantity", "unit"}
            if kitchen_action
            else {"chore_id"}
            if action == "chore_reminder"
            else set()
            if action == "room_checkin"
            else {"location_id"}
        )
        optional = {"action", "room_follow", "room_minutes", "room_location_id"}
        if (
            action
            not in (
                "call_companion",
                "chore_reminder",
                "room_checkin",
                "kitchen_used_up",
                "kitchen_reorder",
            )
            or set(data) - optional != expected
        ):
            raise ValueError("Choose the fields for this tag action")
        follow = data.get("room_follow", action == "room_checkin")
        if type(follow) is not bool or ((action == "call_companion" or kitchen_action) and follow):
            raise ValueError("Use the room check-in action or enable room following on a chore")
        if action == "room_checkin" and not follow:
            raise ValueError("Room check-in requires room following")
        if (
            type(data.get("room_minutes", 10)) is not int
            or not 1 <= data.get("room_minutes", 10) <= 30
        ):
            raise ValueError("Choose a room cue lifetime of 1–30 minutes")
        preferred = data.get("room_location_id", "")
        if not isinstance(preferred, str) or len(preferred) > 100:
            raise ValueError("Choose a room destination")
        if preferred and preferred not in {p["id"] for p in self.locations() if p.get("approved")}:
            raise ValueError("Choose an approved room destination")
        key = tag_id(data["tag_id"])
        if (
            follow
            and preferred
            and self.room_follow
            and self.room_follow.plan(key, data)["status"]
            not in ("ready", "room_screen_unavailable")
        ):
            raise ValueError(
                "Choose a same-room screen, or an approved fallback when that room has no screen"
            )
        if not isinstance(data["name"], str) or not 1 <= len(data["name"].strip()) <= 80:
            raise ValueError("Use a name of 1–80 characters")
        if type(data["enabled"]) is not bool:
            raise ValueError("Choose enabled or disabled")
        if kitchen_action:
            if self.kitchen is None:
                raise ValueError("Kitchen unavailable")
            from .kitchen import number, text

            number(data["quantity"])
            text(data["unit"], 30)
            with self.kitchen.session(active=True, enabled=True) as (store, profile, cfg):
                self.kitchen.get(store, profile, "product", data["product_id"])
        if action == "call_companion":
            if data["location_id"] not in {p["id"] for p in self.locations() if p.get("approved")}:
                raise ValueError("Choose an approved destination")
        elif action == "chore_reminder" and (
            self.chores is None
            or data["chore_id"] not in {v["id"] for v in self.chores.snapshot()["items"]}
        ):
            raise ValueError("Choose a configured chore")
        with self.lock:
            mappings = read(self.folder / "mappings.json", {})
            if len(mappings) >= 100 and key not in mappings:
                raise ValueError("At most 100 mapped tags")
            mappings[key] = {**data, "name": data["name"].strip(), "action": action}
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

    def dispatch(self, key, request_id=None, scanned=False):
        mapping = read(self.folder / "mappings.json", {}).get(tag_id(key))
        if not mapping or not mapping["enabled"]:
            return {"status": "unmapped_or_disabled"}
        follow = mapping.get("room_follow", mapping.get("action") == "room_checkin")
        if follow and not scanned:
            return {"status": "real_scan_required"}
        if mapping.get("action") in ("kitchen_used_up", "kitchen_reorder"):
            if not scanned or self.kitchen is None:
                return {"status": "real_scan_required"}
            try:
                return self.kitchen.tag(
                    mapping["product_id"],
                    mapping["action"],
                    mapping["quantity"],
                    mapping["unit"],
                    request_id,
                )
            except (ValueError, PermissionError):
                return {"status": "kitchen_unavailable_check_dashboard"}
        if mapping.get("action") == "room_checkin":
            return (
                self.room_follow.scan(key, mapping)
                if self.room_follow
                else {"status": "room_follow_unavailable"}
            )
        if mapping.get("action") == "chore_reminder":
            if self.chores is None:
                return {"status": "chore_unavailable"}
            try:
                value = self.chores.complete(mapping["chore_id"], request_id=request_id)["item"]
                result = {
                    "status": "chore_completed",
                    "chore_id": value["id"],
                    "due_at": value["due_at"],
                }
                if follow:
                    room = (
                        self.room_follow.scan(key, mapping)
                        if self.room_follow
                        else {"status": "room_follow_unavailable"}
                    )
                    result["room_status"] = room["status"]
                return result
            except (ValueError, KeyError, TypeError):
                return {"status": "chore_unavailable"}
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
                result = self.dispatch(key, request_id=event, scanned=True)
            state["last_scan"]["status"] = result["status"]
            state["last_scan"]["room_status"] = result.get("room_status")
            write(self.folder / "state.json", state)
            return result

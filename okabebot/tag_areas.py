"""Private, expiring HA tag-to-area configuration; never presence or scan history."""

from contextlib import closing
from pathlib import Path
import math
import threading
import time

from .amadeus import Store
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM
from .presence_control import read, write


def connection_scope(store):
    connection = preference(store, SYSTEM, "feed_connection.ha", {})
    if connection.get("disabled") or not connection.get("url") or not connection.get("token"):
        return None
    return [connection["url"], preference(store, SYSTEM, "feed_connection_revision.ha")]


def cached_areas(store, folder):
    value = read(Path(folder) / "ha-areas.json", {})
    scope = connection_scope(store)
    if scope is None:
        return {"state": "not_connected", "tags": {}}
    checked = value.get("checked_at", 0) if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("scope") != scope
        or type(checked) not in (int, float)
        or not math.isfinite(checked)
        or not 0 <= store.clock() - checked <= 600
        or not isinstance(value.get("tags"), dict)
    ):
        return {"state": "stale", "tags": {}}
    return {
        "state": "ready",
        "tags": {
            k: v
            for k, v in value["tags"].items()
            if isinstance(v, dict)
            and isinstance(v.get("room"), str)
            and (v.get("area_id") is None or isinstance(v.get("area_id"), str))
        },
    }


def chore_rooms(store, folder, chore_id):
    folder = Path(folder).parent / "tags"
    areas = cached_areas(store, folder)
    found = {}
    for key, mapping in read(folder / "mappings.json", {}).items():
        if mapping.get("action") != "chore_reminder" or mapping.get("chore_id") != chore_id:
            continue
        tag = areas["tags"].get(key, {})
        if tag.get("area_id"):
            found[tag["area_id"]] = {
                k: tag.get(k) for k in ("area_id", "room", "floor_id", "floor")
            }
    return sorted(found.values(), key=lambda v: (v["room"], v["area_id"]))


class TagAreas:
    def __init__(self, folder, inventory, clock=time.time):
        self.folder, self.inventory, self.clock = Path(folder), inventory, clock
        self.lock = threading.Lock()

    def snapshot(self):
        with closing(Store(self.folder, clock=self.clock)) as store:
            return cached_areas(store, self.folder.parent / "tags")

    def refresh(self):
        with self.lock:
            with closing(Store(self.folder, clock=self.clock)) as store:
                scope = connection_scope(store)
            if scope is None:
                return self.snapshot()
            try:
                inventory = self.inventory()
                tags = {}
                duplicates = set()
                for tag in inventory.get("tags", []):
                    key = tag["tag_id"]
                    if key in tags:
                        duplicates.add(key)
                    tags[key] = {
                        k: tag.get(k) for k in ("entity_id", "area_id", "room", "floor_id", "floor")
                    }
                for key in duplicates:
                    tags.pop(key, None)
                with closing(Store(self.folder, clock=self.clock)) as store:
                    if connection_scope(store) != scope:
                        return {"state": "context_changed", "tags": {}}
                    write(
                        self.folder.parent / "tags/ha-areas.json",
                        {"scope": scope, "checked_at": self.clock(), "tags": tags},
                    )
            except Exception:
                return {"state": "refresh_failed", "tags": {}}
            return self.snapshot()

    def run(self, stop):
        while not stop.is_set():
            self.refresh()
            stop.wait(300)

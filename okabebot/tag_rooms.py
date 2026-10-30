"""Explicit NFC room cues and single room-based movement requests; no home estimate."""

from contextlib import closing
from pathlib import Path
import time

from .amadeus import Store
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY
from .presence_control import read, write
from .tag_areas import cached_areas


def profile_revision(store):
    row = store.db.execute(
        "SELECT updated_at FROM preferences WHERE subject=? AND key=?", (SYSTEM, KEY)
    ).fetchone()
    return row[0] if row else None


def room_cue(folder, clock=time.time):
    folder = Path(folder)
    cue = read(folder.parent / "tags/room-cue.json", {}) or {}
    if not isinstance(cue, dict) or not cue.get("tag_id"):
        return None
    at, until = cue.get("observed_at", 0), cue.get("expires_at", 0)
    if type(at) not in (int, float) or type(until) not in (int, float) or not at <= clock() < until:
        return None
    with closing(Store(folder, clock=clock)) as store:
        setup = preference(store, SYSTEM, KEY, {})
        if (
            not setup.get("profile")
            or setup.get("paused")
            or setup.get("guest")
            or cue.get("profile") != setup["profile"]
            or cue.get("profile_revision") != profile_revision(store)
        ):
            return None
        mapping = read(folder.parent / "tags/mappings.json", {}).get(cue.get("tag_id"), {})
        if not mapping.get("enabled") or not (
            mapping.get("room_follow") or mapping.get("action") == "room_checkin"
        ):
            return None
        now = clock()
        at, until = cue.get("observed_at", 0), cue.get("expires_at", 0)
        if (
            type(at) not in (int, float)
            or type(until) not in (int, float)
            or not 0 <= now - at <= mapping.get("room_minutes", 10) * 60
            or now >= until
        ):
            return None
        area = cached_areas(store, folder.parent / "tags")["tags"].get(cue.get("tag_id"), {})
        if not area.get("area_id") or area["area_id"] != cue.get("area_id"):
            return None
        return {
            **{k: area.get(k) for k in ("area_id", "room", "floor_id", "floor")},
            "observed_at": at,
            "expires_at": until,
            "evidence": "explicit_nfc_scan",
            "identity": "unknown",
        }


class TagRoomFollow:
    def __init__(self, folder, locations, call, clock=time.time):
        self.folder, self.raw_locations, self.call, self.clock = (
            Path(folder),
            locations,
            call,
            clock,
        )

    def cue(self):
        return room_cue(self.folder, self.clock)

    def locations(self):
        with closing(Store(self.folder, clock=self.clock)) as store:
            bindings = preference(store, SYSTEM, "home_map.bindings", {})
        return [{**p, "area_id": bindings.get(p["id"])} for p in self.raw_locations()]

    def plan(self, key, mapping):
        with closing(Store(self.folder, clock=self.clock)) as store:
            metadata = cached_areas(store, self.folder.parent / "tags")
        area = metadata["tags"].get(key, {})
        if not area.get("area_id"):
            return {"status": "tag_room_unavailable"}
        targets = [
            p for p in self.locations() if p.get("approved") and p.get("area_id") == area["area_id"]
        ]
        preferred = mapping.get("room_location_id")
        if preferred:
            targets = [p for p in targets if p["id"] == preferred]
        if len(targets) != 1:
            return {
                "status": "room_screen_ambiguous" if len(targets) > 1 else "room_screen_unassigned",
                "area": area,
            }
        target = targets[0]
        if target.get("adapter") in ("browser", "mac", "alexa") and not target.get("available"):
            return {"status": "room_screen_unavailable", "area": area}
        return {"status": "ready", "area": area, "location_id": target["id"]}

    def scan(self, key, mapping):
        # Clear the previous cue even if this selected tag now has no known room.
        path = self.folder.parent / "tags/room-cue.json"
        write(path, {})
        plan = self.plan(key, mapping)
        recorded = False
        if plan.get("area"):
            with closing(Store(self.folder, clock=self.clock)) as store:
                setup = preference(store, SYSTEM, KEY, {})
                if setup.get("profile") and not setup.get("paused") and not setup.get("guest"):
                    now = self.clock()
                    write(
                        path,
                        {
                            "tag_id": key,
                            "profile": setup["profile"],
                            "profile_revision": profile_revision(store),
                            "area_id": plan["area"]["area_id"],
                            "observed_at": now,
                            "expires_at": now + mapping.get("room_minutes", 10) * 60,
                        },
                    )
                    recorded = True
        if plan["status"] != "ready":
            return {"status": plan["status"], "room_cue_recorded": recorded}
        if self.plan(key, mapping) != plan:
            return {"status": "room_context_changed", "room_cue_recorded": recorded}
        # Existing movement pipeline owns scene readiness, handoff and manual-follow hold.
        try:
            result = self.call(plan["location_id"])
            status = (
                "already_in_room"
                if result.get("already_there")
                else "room_move_requested"
                if result.get("accepted") is not False and not result.get("error")
                else "room_move_failed"
            )
        except Exception:
            status = "room_move_failed"
        return {"status": status, "room_cue_recorded": recorded}

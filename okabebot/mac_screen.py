"""Coarse paired Mac display state and owner-configured wake handoff. No history."""

import math
from pathlib import Path
import threading
import time

from .presence_control import read, write, manual_move

DEFAULTS = {
    "enabled": False,
    "destination": "",
    "respect_media": True,
    "respect_manual_hold": True,
    "cooldown_seconds": 60,
}


class MacScreen:
    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = Path(folder), clock
        self.lock = threading.RLock()
        self.current = {}  # Process-local only; no restored awake state after restart.
        self.last_attempt = 0
        self.reason = "waiting for Mac display"

    def settings(self):
        return {**DEFAULTS, **read(self.folder / "mac-screen.json", {})}

    def configure(self, data, places):
        if not isinstance(data, dict) or set(data) != set(DEFAULTS):
            raise ValueError("Use supported Mac wake options")
        if any(
            type(data[k]) is not bool for k in ("enabled", "respect_media", "respect_manual_hold")
        ):
            raise ValueError("Use boolean wake options")
        if type(data["cooldown_seconds"]) is not int or not 10 <= data["cooldown_seconds"] <= 3600:
            raise ValueError("Choose a cooldown from 10 to 3600 seconds")
        if data["destination"] and not any(
            p["id"] == data["destination"] and p["adapter"] == "mac" and p["approved"]
            for p in places
        ):
            raise ValueError("Choose an approved Mac destination")
        if data["enabled"] and not data["destination"]:
            raise ValueError("Choose a Mac destination")
        with self.lock:
            write(self.folder / "mac-screen.json", data)
            self.reason = "waiting for next display wake" if data["enabled"] else "disabled"
        return self.snapshot()

    def snapshot(self):
        with self.lock:
            cfg = self.settings()
            value = self.current.get(cfg["destination"], {})
            fresh = 0 <= self.clock() - value.get("observed_at", 0) <= 75
            return {
                "config": cfg,
                "state": value.get("state", "unknown") if fresh else "unknown",
                "fresh": fresh,
                "reason": self.reason,
            }

    def signal(self, item, data, snapshot, move):
        if item.get("adapter") != "mac" or not item.get("approved"):
            raise PermissionError("Approved Mac surface required")
        if not isinstance(data, dict) or set(data) != {"state", "cause", "observed_at", "event_id"}:
            raise ValueError("Invalid display signal")
        now, stamp = self.clock(), data["observed_at"]
        if (
            type(stamp) not in (int, float)
            or not math.isfinite(stamp)
            or not 0 <= now - stamp <= 30
            or data["state"] not in ("on", "off")
            or data["cause"] not in ("wake", "sleep", "snapshot")
            or not isinstance(data["event_id"], str)
            or not 1 <= len(data["event_id"]) <= 64
        ):
            raise ValueError("Use a fresh bounded display signal")
        if (data["cause"] == "wake" and data["state"] != "on") or (
            data["cause"] == "sleep" and data["state"] != "off"
        ):
            raise ValueError("Display cause/state mismatch")
        state = snapshot() if data["cause"] == "wake" else {}
        with self.lock:
            old = self.current.get(item["id"], {})
            if stamp < old.get("observed_at", 0):
                return {"accepted": False, "reason": "older signal"}
            value = {**data, "last_wake_at": old.get("last_wake_at", 0)}
            self.current[item["id"]] = value
            cfg = self.settings()
            if data["cause"] != "wake":
                return {"accepted": True, "moved": False}
            if stamp <= value["last_wake_at"]:
                return {"accepted": False, "reason": "duplicate wake"}
            value["last_wake_at"] = stamp  # Consume even blocked/uncertain moves.
            reason = None
            surfaces = state.get("surfaces", {})
            if not cfg["enabled"] or cfg["destination"] != item["id"]:
                reason = "disabled or different Mac"
            elif (
                state.get("busy") or state.get("recording") or state.get("focus", {}).get("active")
            ):
                reason = "busy or focus"
            elif cfg["respect_media"] and (
                state.get("music", {}).get("is_playing") or state.get("tv", {}).get("is_playing")
            ):
                reason = "media playing"
            elif surfaces.get("phase") not in ("pi", "tv"):
                reason = "already moving"
            elif surfaces.get("current_location") == item["id"]:
                reason = "already here"
            elif cfg["respect_manual_hold"] and now < read(
                self.folder / "home-presence/follow.json", {}
            ).get("manual_hold_until", 0):
                reason = "manual location hold"
            elif now - self.last_attempt < cfg["cooldown_seconds"]:
                reason = "cooldown"
            if reason:
                self.reason = reason
                return {"accepted": True, "moved": False, "reason": reason}
            self.last_attempt = now
            # Hold BLE following after a stronger, explicit screen wake cue.
            manual_move(self.folder)
            self.reason = "handoff requested"
            try:
                result = move(item["id"])
            except Exception:
                self.reason = "handoff unavailable; no replay"
                return {"accepted": True, "moved": False, "reason": self.reason}
            return {"accepted": True, "moved": bool(result.get("accepted")), "reason": self.reason}

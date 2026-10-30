"""Supervised following over the home bridge's existing observations."""

import json
import time
from pathlib import Path
from urllib.request import Request, urlopen
from .ble_follow import AnchorGate
from . import presence_control


class Following:
    def __init__(self, folder, config):
        self.folder, self.config = Path(folder), config
        self.gate = AnchorGate(
            [a["id"] for a in config["anchors"]], **config.get("follow_gate", {})
        )
        self.next_check = 0
        self.reason = "disabled"
        self.expected = None

    def request(self, path, data=None):
        control = json.loads(Path(self.config["control_file"]).read_text())
        base, token = control["url"].split("#", 1)
        req = Request(
            base.rstrip("/") + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"X-Hardware-Token": token, "Content-Type": "application/json"},
        )
        with urlopen(req, timeout=10) as response:
            return json.load(response)

    def step(self, now, healthy):
        if now < self.next_check:
            return self.reason
        self.next_check = now + 2
        status = presence_control.status(self.folder)
        self.reason = "disabled"
        if not status["follow_enabled"]:
            self.gate.candidate = None
            self.expected = None
            return self.reason
        held = time.time() < status.get("manual_hold_until", 0)
        if healthy != 2 or held:
            self.reason = "manual hold" if held else "scanner unavailable"
            self.gate.candidate = None
            return self.reason
        last = presence_control.read(self.folder / "home-presence/follow-request.json", {}).get(
            "at", 0
        )
        if 0 <= time.time() - last < self.gate.cooldown:
            self.gate.candidate = None
            self.reason = "cooldown"
            return self.reason
        try:
            state = self.request("/state")
            surface = state["surfaces"]
            current = surface.get("current_location")
            if surface.get("phase") in ("pi", "tv"):
                if self.expected is not None and current != self.expected:
                    presence_control.manual_move(self.folder)
                    self.reason = "manual hold"
                    self.gate.candidate = None
                    self.expected = current
                    return self.reason
                self.expected = current
            busy = (
                state.get("busy")
                or state.get("recording")
                or state.get("focus", {}).get("active")
                or state.get("music", {}).get("is_playing")
                or state.get("tv", {}).get("is_playing")
            )
            blocked = busy or surface["phase"] not in ("pi", "tv")
            self.reason = "busy" if busy else "moving" if blocked else "observing"
            target = self.gate.choose(now, surface.get("current_location"), blocked)
            if target:
                presence_control.write(
                    self.folder / "home-presence/follow-request.json",
                    {"at": time.time(), "target": target},
                )
                self.request("/presence/move", {"location_id": target})
                self.expected = target
                self.reason = "handoff requested"
        except Exception:
            self.reason = "controller or destination unavailable"
            self.gate.candidate = None
        return self.reason

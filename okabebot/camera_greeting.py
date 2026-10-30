"""Opt-in anonymous face greeting: home + fresh near-anchor evidence before capture.

No face identity, recording, cloud calls or persisted images. Presence is a device
estimate, not a guarantee that the observed person is the owner.
"""

import base64
import time
from .presence_control import read, write, status as presence_status
from .config import state_dir
from .hardware import rpc
from . import scene


DEFAULTS = {
    "allow_during_media": False,
    "require_home": True,
    "enabled": False,
    "source": "camera",
    "near_mm": 800,
    "far_mm": 1100,
    "dwell_seconds": 2,
    "cooldown_seconds": 120,
}


def settings():
    return {**DEFAULTS, **read(state_dir() / "camera-greeting.json", {})}


def configure(data):
    if not isinstance(data, dict) or not data or set(data) - set(DEFAULTS):
        raise ValueError("Unsupported greeting setting")
    cfg = {**settings(), **data}
    if (
        type(cfg["enabled"]) is not bool
        or type(cfg["allow_during_media"]) is not bool
        or type(cfg["require_home"]) is not bool
        or cfg["source"] not in ("camera", "ultrasonic")
    ):
        raise ValueError("Choose greeting enabled and source")
    for key, lo, hi in [
        ("near_mm", 100, 3000),
        ("far_mm", 100, 4000),
        ("dwell_seconds", 1, 30),
        ("cooldown_seconds", 10, 3600),
    ]:
        if type(cfg[key]) is not int or not lo <= cfg[key] <= hi:
            raise ValueError("Greeting setting outside supported range")
    if cfg["far_mm"] <= cfg["near_mm"]:
        raise ValueError("Far distance must exceed near distance")
    write(state_dir() / "camera-greeting.json", cfg)
    return cfg


def permitted(
    presence, snapshot, now=None, *, ultrasonic=False, allow_media=False, require_home=True
):
    now = time.time() if now is None else now
    surface = snapshot.get("surfaces", {})
    place = next(
        (p for p in surface.get("locations", []) if p.get("id") == surface.get("current_location")),
        {},
    )
    return bool(
        (
            (ultrasonic and not require_home)
            or (
                presence.get("fresh")
                and 0 <= now - presence.get("updated_at", 0) <= 10
                and presence.get("presence") == "home"
            )
        )
        and (
            ultrasonic
            or (
                presence.get("healthy_scanners") == 2
                and presence.get("nearby_location") == place.get("id")
            )
        )
        and place.get("approved")
        and place.get("adapter") == "pi"
        and surface.get("phase") == "pi"
        and not snapshot.get("busy")
        and not snapshot.get("recording")
        and not snapshot.get("focus", {}).get("active")
        and (allow_media or not snapshot.get("music", {}).get("is_playing"))
        and (allow_media or not snapshot.get("tv", {}).get("is_playing"))
    )


class Gate:
    def __init__(self):
        self.dwell_seconds = 2
        self.cooldown_seconds = 120
        self.since = None
        self.last_seen = None
        self.last_check = None
        self.armed = True
        self.blocked_since = None
        self.last_wave = -1e9

    def observe(self, found, now, allowed=True):
        if not allowed:
            self.since = None
            self.last_check = None
            if self.blocked_since is None:
                self.blocked_since = now
            return False
        if self.blocked_since is not None:
            if now - self.blocked_since >= 15:
                self.armed = True
            self.blocked_since = None
        if self.last_check is not None and now - self.last_check > 15:
            self.since = None
        self.last_check = now
        if not found:
            # Tolerate one missed face frame, but never stale/blocked presence.
            if self.last_seen is None or now - self.last_seen >= 8:
                self.since = None
            if self.last_seen is not None and now - self.last_seen >= 15:
                self.armed = True
            return False
        self.last_seen = now
        if self.since is None:
            self.since = now
        if (
            self.armed
            and now - self.since >= self.dwell_seconds
            and now - self.last_wave >= self.cooldown_seconds
        ):
            self.armed = False
            self.last_wave = now  # consume before sending; no uncertain retries
            return True
        return False


class Detector:
    def __init__(self):
        import cv2

        self.cv = cv2
        self.cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        if self.cascade.empty():
            raise RuntimeError("Face detector unavailable")

    def detect(self, jpeg):
        import numpy as np

        frame = self.cv.imdecode(np.frombuffer(jpeg, dtype=np.uint8), self.cv.IMREAD_GRAYSCALE)
        if frame is None or frame.shape[0] > 480 or frame.shape[1] > 640:
            raise ValueError("Invalid detection image")
        # Center 80% of frame; require a reasonably sized frontal face.
        height, width = frame.shape
        crop = frame[int(height * 0.1) : int(height * 0.9), int(width * 0.1) : int(width * 0.9)]
        faces = self.cascade.detectMultiScale(
            self.cv.equalizeHist(crop), scaleFactor=1.1, minNeighbors=6, minSize=(45, 45)
        )
        return len(faces) > 0


class CameraGreeting:
    def __init__(self, bridge):
        self.bridge = bridge
        self.gate = Gate()
        self.detector = None
        self.near = False
        self.state = {
            "enabled": False,
            "status": "disabled",
            "images_saved": False,
            "wave_count": 0,
            "last_wave_at": None,
        }

    def allowed(self):
        return settings().get("enabled") is True and permitted(
            presence_status(state_dir()),
            self.bridge.snapshot(),
            allow_media=settings().get("allow_during_media", False),
        )

    def ultrasonic_step(self, cfg):
        self.gate.dwell_seconds = cfg["dwell_seconds"]
        self.gate.cooldown_seconds = cfg["cooldown_seconds"]
        sensors = rpc({"op": "room_sensors"})
        distance = sensors.get("distance_mm")
        valid = (
            sensors.get("connected") is True and type(distance) is int and 20 <= distance <= 4000
        )
        self.near = valid and distance <= (cfg["far_mm"] if self.near else cfg["near_mm"])
        self.state.update(
            settings=cfg,
            enabled=cfg["enabled"],
            sensors=sensors,
            nearby=self.near if valid else None,
            status="object nearby" if self.near else "waiting for proximity",
        )
        presence = presence_status(state_dir())
        # Home gating is optional only for explicitly enabled anonymous ultrasound.
        snapshot = self.bridge.snapshot()
        allowed = cfg["enabled"] and permitted(
            presence,
            snapshot,
            ultrasonic=True,
            allow_media=cfg["allow_during_media"],
            require_home=cfg["require_home"],
        )
        now = time.monotonic()
        if not valid:
            self.state["status"] = "ultrasonic sensor unavailable"
            self.gate.observe(False, now, allowed=False)
            return
        if not allowed:
            self.state["status"] = (
                (
                    "waiting for home and an available companion display"
                    if cfg["require_home"]
                    else "waiting for an available companion display"
                )
                if cfg["enabled"]
                else "greeting disabled; sensors available"
            )
        if self.gate.observe(self.near, now, allowed=allowed):
            if (
                not self.bridge.closing.is_set()
                and settings() == cfg
                and permitted(
                    presence_status(state_dir()),
                    self.bridge.snapshot(),
                    ultrasonic=True,
                    allow_media=cfg["allow_during_media"],
                    require_home=cfg["require_home"],
                )
            ):
                result = scene.wave(allow_during_media=settings().get("allow_during_media", False))
                if not result.get("waved"):
                    self.state["status"] = "wave skipped: " + str(
                        result.get("reason", "renderer unavailable")
                    )
                if result.get("waved"):
                    self.state.update(
                        status="waved",
                        wave_count=self.state["wave_count"] + 1,
                        last_wave_at=time.time(),
                    )

    def step(self):
        cfg = settings()
        if cfg.get("source") == "ultrasonic":
            return self.ultrasonic_step(cfg)
        self.state["settings"] = cfg
        enabled = settings().get("enabled") is True
        self.state.update(
            enabled=enabled, status="waiting for home and nearby Watch" if enabled else "disabled"
        )
        now = time.monotonic()
        if not self.allowed():
            self.gate.observe(False, now, allowed=False)
            return
        if self.detector is None:
            self.detector = Detector()
        self.state["status"] = "checking for a face"
        result = rpc({"op": "camera_probe"})
        if result.get("error"):
            raise RuntimeError("Camera unavailable or busy")
        raw = base64.b64decode(result["jpeg_base64"], validate=True)
        if len(raw) > 300000:
            raise ValueError("Detection frame too large")
        found = self.detector.detect(raw)
        del raw, result
        # Recheck all gates after capture/inference; discard if context changed.
        allowed = self.allowed()
        if self.gate.observe(found, time.monotonic(), allowed):
            if self.allowed():
                result = scene.wave(allow_during_media=settings().get("allow_during_media", False))
                self.state["status"] = "waved" if result.get("waved") else "wave skipped"
                if result.get("waved"):
                    self.state["wave_count"] += 1
                    self.state["last_wave_at"] = time.time()
        elif allowed:
            self.state["status"] = "face present" if found else "no face in view"

    def run(self):
        while not self.bridge.closing.is_set():
            try:
                self.step()
            except Exception:
                self.state.update(
                    status="greeting sensor unavailable; waiting for recovery",
                    sensors={},
                    nearby=None,
                )
                self.near = False
                self.gate.observe(False, time.monotonic(), allowed=False)
            self.bridge.closing.wait(3)

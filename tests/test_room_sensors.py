"""Invented serial packets and freshness; no hardware or participant readings."""

import unittest
from pi.room_sensors import Samples
from okabebot.ha_companion import room_discovery
from okabebot.camera_greeting import permitted


class RoomTests(unittest.TestCase):
    def test_separate_freshness_null_echo_and_disconnect(self):
        now = [0]
        s = Samples(clock=lambda: now[0])
        s.accept({"sensor": "ultrasonic", "distance_mm": 420})
        s.accept(
            {"sensor": "room", "temperature_c": 21, "humidity_percent": 45, "tilt_closed": False}
        )
        self.assertEqual(s.snapshot()["distance_mm"], 420)
        now[0] = 7
        s.accept(
            {"sensor": "room", "temperature_c": 22, "humidity_percent": 46, "tilt_closed": True}
        )
        self.assertIsNone(s.snapshot()["distance_mm"])
        self.assertEqual(s.snapshot()["temperature_c"], 22)
        s.accept({"sensor": "ultrasonic", "distance_mm": float("nan")})
        self.assertIsNone(s.snapshot()["distance_mm"])
        s.accept({"sensor": "ultrasonic", "distance_mm": None})
        self.assertIsNone(s.snapshot()["distance_mm"])
        s.clear()
        self.assertFalse(s.snapshot()["connected"])

    def test_discovery_unavailable_for_null_and_expiry(self):
        values = list(room_discovery("lab/test", "test", "Example", "Study"))
        self.assertEqual(len(values), 5)
        for _, cfg in values:
            self.assertEqual(cfg["availability_mode"], "all")
            self.assertEqual(cfg["expire_after"], 45)
            self.assertIn("is not none", cfg["availability"][1]["value_template"])

    def test_ultrasound_replaces_nearby_gate_but_not_home_or_media(self):
        presence = {"fresh": True, "updated_at": 100, "presence": "home"}
        snapshot = {
            "surfaces": {
                "current_location": "desk",
                "phase": "pi",
                "locations": [{"id": "desk", "approved": True, "adapter": "pi"}],
            }
        }
        self.assertTrue(permitted(presence, snapshot, 100, ultrasonic=True))
        self.assertFalse(permitted(presence, snapshot, 100))
        self.assertFalse(permitted(dict(presence, presence="away"), snapshot, 100, ultrasonic=True))
        self.assertFalse(
            permitted(presence, dict(snapshot, music={"is_playing": True}), 100, ultrasonic=True)
        )
        self.assertFalse(permitted(presence, snapshot, 120, ultrasonic=True))

    def test_ultrasonic_hysteresis_never_uses_camera_and_missing_echo_is_unknown(self):
        from unittest.mock import Mock, patch
        from okabebot.camera_greeting import CameraGreeting, DEFAULTS

        greeting = CameraGreeting(Mock())
        greeting.gate = Mock()
        greeting.gate.observe.return_value = False
        cfg = {**DEFAULTS, "source": "ultrasonic", "enabled": True}
        with (
            patch("okabebot.camera_greeting.rpc") as rpc,
            patch("okabebot.camera_greeting.permitted", return_value=True),
            patch(
                "okabebot.camera_greeting.presence_status",
                return_value={"fresh": True, "presence": "home"},
            ),
            patch("okabebot.camera_greeting.Detector") as camera,
        ):
            for distance, nearby in [(700, True), (950, True), (1200, False), (None, None)]:
                rpc.return_value = {"connected": True, "distance_mm": distance}
                greeting.ultrasonic_step(cfg)
                self.assertEqual(greeting.state["nearby"], nearby)
            self.assertEqual(rpc.call_args.args[0], {"op": "room_sensors"})
            camera.assert_not_called()

    def test_silent_wave_media_exception_preserves_other_gates(self):
        presence = {"fresh": True, "updated_at": 100, "presence": "home"}
        snapshot = {
            "surfaces": {
                "current_location": "desk",
                "phase": "pi",
                "locations": [{"id": "desk", "approved": True, "adapter": "pi"}],
            },
            "tv": {"is_playing": True},
            "music": {"is_playing": True},
        }
        self.assertFalse(permitted(presence, snapshot, 100, ultrasonic=True))
        self.assertTrue(permitted(presence, snapshot, 100, ultrasonic=True, allow_media=True))
        for change in [{"focus": {"active": True}}, {"recording": True}, {"busy": True}]:
            self.assertFalse(
                permitted(presence, {**snapshot, **change}, 100, ultrasonic=True, allow_media=True)
            )
        self.assertFalse(
            permitted(
                dict(presence, presence="away"), snapshot, 100, ultrasonic=True, allow_media=True
            )
        )

    def test_renderer_honors_media_exception_without_bypassing_busy_or_away(self):
        from pi.gesture_policy import wave_allowed

        args = [{"activity": "idle"}, "home", None, {"video": True}, False]
        self.assertFalse(wave_allowed(*args))
        self.assertTrue(wave_allowed(*args, allow_media=True))
        self.assertFalse(wave_allowed(*args, allow_media="true"))
        for index, value in [
            (0, {"activity": "speaking"}),
            (1, "away"),
            (2, {"title": "Example"}),
            (4, True),
        ]:
            changed = list(args)
            changed[index] = value
            self.assertFalse(wave_allowed(*changed, allow_media=True))

    def test_anonymous_ultrasound_is_explicit_and_does_not_relax_camera_policy(self):
        snapshot = {
            "surfaces": {
                "current_location": "desk",
                "phase": "pi",
                "locations": [{"id": "desk", "approved": True, "adapter": "pi"}],
            }
        }
        self.assertFalse(permitted({}, snapshot, 100, ultrasonic=True))
        self.assertTrue(permitted({}, snapshot, 100, ultrasonic=True, require_home=False))
        self.assertFalse(permitted({}, snapshot, 100, require_home=False))
        self.assertFalse(
            permitted({}, dict(snapshot, busy=True), 100, ultrasonic=True, require_home=False)
        )
        self.assertFalse(
            permitted(
                {}, dict(snapshot, focus={"active": True}), 100, ultrasonic=True, require_home=False
            )
        )
        self.assertFalse(
            permitted(
                {},
                dict(snapshot, surfaces={**snapshot["surfaces"], "phase": "away"}),
                100,
                ultrasonic=True,
                require_home=False,
            )
        )

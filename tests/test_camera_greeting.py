"""Synthetic privacy gates and transient visuals, no real camera or person images."""

import unittest
from unittest.mock import Mock, patch
from okabebot.camera_greeting import Gate, CameraGreeting, permitted
from okabebot.ble_follow import AnchorGate


class CameraGreetingTests(unittest.TestCase):
    def setUp(self):
        self.presence = dict(
            fresh=True, updated_at=100, presence="home", healthy_scanners=2, nearby_location="desk"
        )
        self.snapshot = dict(
            surfaces=dict(
                current_location="desk",
                phase="pi",
                locations=[dict(id="desk", adapter="pi", approved=True)],
            )
        )

    def test_unknown_away_weak_or_stale_blocks_camera(self):
        self.assertTrue(permitted(self.presence, self.snapshot, 100))
        for change in (
            dict(presence="unknown"),
            dict(presence="probably_away"),
            dict(nearby_location=None),
            dict(updated_at=80),
            dict(updated_at=101),
            dict(healthy_scanners=1),
            dict(fresh=False),
        ):
            self.assertFalse(permitted({**self.presence, **change}, self.snapshot, 100))
        for change in (
            dict(busy=True),
            dict(recording=True),
            dict(focus={"active": True}),
            dict(music={"is_playing": True}),
            dict(tv={"is_playing": True}),
        ):
            self.assertFalse(permitted(self.presence, {**self.snapshot, **change}, 100))

    @patch("okabebot.camera_greeting.rpc")
    @patch("okabebot.camera_greeting.settings", return_value={"enabled": True})
    def test_blocked_step_never_opens_camera_or_detector(self, settings, rpc):
        bridge = Mock()
        greeting = CameraGreeting(bridge)
        greeting.allowed = Mock(return_value=False)
        with patch("okabebot.camera_greeting.Detector") as detector:
            greeting.step()
        rpc.assert_not_called()
        detector.assert_not_called()

    @patch("okabebot.camera_greeting.scene.wave")
    @patch("okabebot.camera_greeting.settings", return_value={"enabled": True})
    @patch("okabebot.camera_greeting.rpc", return_value={"jpeg_base64": "eA=="})
    def test_home_gate_is_rechecked_after_frame(self, rpc, settings, wave):
        greeting = CameraGreeting(Mock())
        greeting.allowed = Mock(side_effect=[True, False])
        greeting.detector = Mock()
        greeting.detector.detect.return_value = True
        greeting.step()
        rpc.assert_called_once_with({"op": "camera_probe"})
        wave.assert_not_called()

    def test_dwell_cooldown_and_leave_before_rearming(self):
        g = Gate()
        self.assertFalse(g.observe(True, 0))
        self.assertTrue(g.observe(True, 3))
        self.assertFalse(g.observe(True, 130))
        self.assertFalse(g.observe(False, 131))
        self.assertFalse(g.observe(False, 146))
        self.assertFalse(g.observe(True, 147))
        self.assertTrue(g.observe(True, 150))

    def test_strong_nearby_anchor_ignores_follow_cooldown_but_not_ambiguity(self):
        gate = AnchorGate(["desk", "upstairs"])
        for stamp in (98, 99, 100):
            gate.update("desk", -60, stamp)
        self.assertEqual(gate.nearby(100), "desk")
        self.assertIsNone(gate.nearby(111))
        gate.update("upstairs", -61, 100)
        self.assertIsNone(gate.nearby(100))

    def test_wave_renders_for_all_characters_without_phone_prop(self):
        from pi import scene

        for style in ("okabe", "kurisu", "pip", "sonic"):
            a = scene.render(style=style, gesture="wave", phase=0)
            b = scene.render(style=style, gesture="wave", phase=0.2)
            self.assertEqual(a.size, (480, 320))
            self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_one_missed_face_frame_is_tolerated_but_blocked_context_resets_dwell(self):
        g = Gate()
        self.assertFalse(g.observe(True, 0))
        self.assertFalse(g.observe(False, 3))
        self.assertTrue(g.observe(True, 6))
        g = Gate()
        self.assertFalse(g.observe(True, 0))
        self.assertFalse(g.observe(False, 3, allowed=False))
        self.assertFalse(g.observe(True, 6))

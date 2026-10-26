import unittest
import time
import math
from pi import scene, pip_face
from okabebot.profiles import PROFILES


class IdleTests(unittest.TestCase):
    def test_phone_replaces_resting_arm_and_follows_body_bob(self):
        for style, sleeve, resting_bottom in (
            ("okabe", "#e9e5dc", 73),
            ("kurisu", "#b5997a", 74),
        ):
            for phase in (1, 3):
                bob = round(math.sin(phase * 1.7))
                resting = scene.shapes(style=style, phase=phase)
                phone = scene.shapes(style=style, phase=phase, idle_seconds=38)
                # No second arm remains below the raised elbow.
                self.assertTrue(
                    any(
                        fill == sleeve
                        and coords[0] >= 308
                        and coords[3] == (resting_bottom + bob) * 4 - 1
                        for kind, coords, fill, _ in resting
                        if kind == "rectangle"
                    )
                )
                self.assertFalse(
                    any(
                        fill == sleeve and coords[0] >= 308 and coords[3] > (66 + bob) * 4 - 1
                        for kind, coords, fill, _ in phone
                        if kind == "rectangle"
                    )
                )
                self.assertIn(
                    ("rectangle", (312, (32 + bob) * 4, 335, (45 + bob) * 4 - 1), "#131a24", 1),
                    phone,
                )
                # The opposite resting sleeve remains in place.
                self.assertEqual(
                    [s for s in resting if s[2] == sleeve and s[1][0] < 140],
                    [s for s in phone if s[2] == sleeve and s[1][0] < 140],
                )

    def test_idle_yields_to_activity_and_overlays(self):
        for style in ("kurisu", "okabe", "sonic"):
            self.assertNotEqual(
                scene.shapes(style=style, phase=1, idle_seconds=38),
                scene.shapes(style=style, phase=1, idle_seconds=0),
            )
            for kwargs in (
                {"activity": "speaking"},
                {"notification": {"title": "Hi", "body": "", "source": "system"}},
                {"music": {"is_playing": True}},
                {"deploying": True},
            ):
                self.assertEqual(
                    scene.shapes(style=style, phase=1, idle_seconds=38, **kwargs),
                    scene.shapes(style=style, phase=1, idle_seconds=0, **kwargs),
                )

    def test_music_excitement_has_no_alert_decoration(self):
        music = {
            "is_playing": True,
            "meter_active": True,
            "pulse_at": time.monotonic(),
            "expression": "excited",
        }
        self.assertFalse(
            any(
                shape[2] == "#f2ca70"
                for shape in scene.shapes(style="kurisu", phase=1, music=music)
            )
        )
        self.assertTrue(
            any(
                shape[2] == "#f2ca70"
                for shape in scene.shapes(style="kurisu", phase=1, emotion="excited")
            )
        )

    def test_sonic_profile_and_render(self):
        self.assertEqual(PROFILES["sonic"]["style"], "sonic")
        self.assertEqual(pip_face.render(style="sonic").size, (480, 320))

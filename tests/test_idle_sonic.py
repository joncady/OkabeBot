import unittest
import time
from pi import scene, pip_face
from okabebot.profiles import PROFILES


class IdleTests(unittest.TestCase):
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

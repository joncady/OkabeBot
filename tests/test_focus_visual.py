"""Synthetic Pi timer projection/render checks; no Tk display or physical side effects."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pi.focus_visual import Focus, badge, visible, overlay, BADGE_POSITION


class FocusVisualTests(unittest.TestCase):
    def test_strict_bounded_state_expires_locally_and_cancel_clears(self):
        focus = Focus()
        self.assertEqual(
            60,
            focus.command({"op": "focus", "active": True, "ends_at": 1060}, now=1000)[
                "remaining_seconds"
            ],
        )
        self.assertEqual(1, focus.status(now=1059.9)["remaining_seconds"])
        self.assertFalse(focus.status(now=1060)["active"])
        focus.command({"op": "focus", "active": True, "ends_at": 1100}, now=1000)
        self.assertFalse(
            focus.command({"op": "focus", "active": False, "ends_at": None}, now=1000)["active"]
        )
        for value in (True, float("nan"), float("inf"), 994, 12000, "1060"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                focus.command({"op": "focus", "active": True, "ends_at": value}, now=1000)
        for value in (
            {"op": "focus", "active": 1, "ends_at": 1060},
            {"op": "focus", "active": False, "ends_at": 1060},
            {"op": "focus", "active": False, "ends_at": None, "action": "speak"},
        ):
            with self.assertRaises(ValueError):
                focus.command(value, now=1000)
        self.assertFalse(Focus().status(now=1000)["active"])

    def test_quiet_pose_does_not_override_interaction_media_notifications_or_travel(self):
        focus = Focus()
        focus.command({"op": "focus", "active": True, "ends_at": 1060}, now=1000)
        args = {
            "activity": "idle",
            "emotion": "excited",
            "intensity": 0.8,
            "mouth": 0.6,
            "phase": 40,
            "idle_seconds": 100,
            "gesture": "idle",
        }
        quiet = focus.quiet_args(args, now=1000)
        self.assertEqual(
            ("neutral", 0, 0, 10),
            (quiet["emotion"], quiet["mouth"], quiet["idle_seconds"], quiet["phase"]),
        )
        for activity in ("speaking", "listening", "thinking"):
            value = dict(args, activity=activity)
            self.assertIs(value, focus.quiet_args(value, now=1000))
        self.assertIs(args, focus.quiet_args(args, blocked=True, now=1000))
        waving = dict(args, gesture="wave")
        self.assertIs(waving, focus.quiet_args(waving, now=1000))
        self.assertTrue(visible(True, args))
        for kwargs in (
            {"phase": "away"},
            {"phase": "departing"},
            {"notification": {"title": "notice"}},
            {"music": {"is_playing": True}},
            {"music": {"video": {"title": "video"}}},
            {"deploying": True},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(visible(True, args, **kwargs))

    def test_badge_is_small_pixel_art_and_changes_with_remaining_time(self):
        a, b = badge(65), badge(64)
        self.assertEqual((104, 32), a.size)
        self.assertEqual("RGBA", a.mode)
        self.assertNotEqual(a.tobytes(), b.tobytes())
        self.assertIsNone(a.getpixel((0, 0))[3] or None)

    def test_high_level_scene_api_sends_only_timer_state(self):
        from okabebot import scene

        with patch("okabebot.scene.rpc", return_value={"active": True}) as rpc:
            scene.set_focus({"active": True, "ends_at": 1060, "id": "not-rendered"})
        rpc.assert_called_once_with({"op": "focus", "active": True, "ends_at": 1060})

    def test_real_draw_method_hides_overlay_while_media_or_travel_has_priority(self):
        import time

        tree = ast.parse((Path(__file__).parents[1] / "pi/service.py").read_text())
        display = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Display")
        method = next(
            n for n in display.body if isinstance(n, ast.FunctionDef) and n.name == "draw_focus"
        )
        namespace = {"focus_visual": __import__("pi.focus_visual", fromlist=["Focus"])}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "service.py", "exec"), namespace)
        focus = Focus()
        focus.command({"op": "focus", "active": True, "ends_at": time.time() + 60})
        for phase, music in [("away", {}), ("departing", {}), ("home", {"is_playing": True})]:
            fake = SimpleNamespace(
                focus=focus,
                character={"activity": "idle"},
                motion=SimpleNamespace(phase=phase),
                notification=None,
                music=music,
                deploying=False,
                focus_item=42,
                focus_shown=True,
                canvas=Mock(),
            )
            namespace["draw_focus"](fake, 1, 1)
            fake.canvas.itemconfigure.assert_called_once_with(42, state="hidden")
            self.assertFalse(fake.focus_shown)

    def test_preview_overlay_changes_only_top_corner_and_preserves_priority(self):
        from PIL import Image, ImageChops

        image = Image.new("RGB", (480, 320), "#101923")
        status = {"active": True, "remaining_seconds": 65}
        self.assertIs(image, overlay(image, status, False))
        result = overlay(image, status, True)
        bounds = ImageChops.difference(image.convert("RGBA"), result).convert("RGB").getbbox()
        x, y = BADGE_POSITION
        self.assertTrue(x <= bounds[0] < bounds[2] <= x + 104)
        self.assertTrue(y <= bounds[1] < bounds[3] <= y + 32)
        self.assertEqual("#101923", "#%02x%02x%02x" % image.getpixel((x + 1, y + 1)))

    def test_quiet_scene_renders_for_every_character_without_extra_phone_gestures(self):
        from pi import scene

        focus = Focus()
        focus.command({"op": "focus", "active": True, "ends_at": 1060}, now=1000)
        for style in ("okabe", "kurisu", "pip", "sonic"):
            args = focus.quiet_args(
                {
                    "style": style,
                    "activity": "idle",
                    "emotion": "excited",
                    "phase": 101,
                    "intensity": 0.8,
                    "idle_seconds": 300,
                    "gesture": "idle",
                },
                now=1000,
            )
            image = scene.render(**args)
            self.assertEqual((480, 320), image.size)
            self.assertEqual(0, args["idle_seconds"])

    def test_real_draw_method_retains_tk_item_and_updates_only_changed_second(self):
        import base64
        import io
        from PIL import Image
        from pi import focus_visual

        tree = ast.parse((Path(__file__).parents[1] / "pi/service.py").read_text())
        display = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Display")
        method = next(
            n for n in display.body if isinstance(n, ast.FunctionDef) and n.name == "draw_focus"
        )
        photo = Mock(side_effect=[object(), object()])
        namespace = {
            "focus_visual": focus_visual,
            "tk": SimpleNamespace(PhotoImage=photo),
            "base64": base64,
            "io": io,
            "Image": Image,
        }
        exec(compile(ast.Module(body=[method], type_ignores=[]), "service.py", "exec"), namespace)
        focus = Mock()
        focus.status.return_value = {"active": True, "remaining_seconds": 65}
        fake = SimpleNamespace(
            focus=focus,
            character={"activity": "idle"},
            motion=SimpleNamespace(phase="home"),
            notification=None,
            music={},
            deploying=False,
            focus_item=None,
            focus_shown=False,
            focus_key=None,
            focus_photo=None,
            scene_rebuilt=False,
            canvas=Mock(),
        )
        fake.canvas.create_image.return_value = 42
        namespace["draw_focus"](fake, 2, 1.875)
        namespace["draw_focus"](fake, 2, 1.875)
        self.assertEqual(1, photo.call_count)
        focus.status.return_value = {"active": True, "remaining_seconds": 64}
        namespace["draw_focus"](fake, 2, 1.875)
        self.assertEqual(2, photo.call_count)
        fake.canvas.create_image.assert_called_once()
        fake.canvas.tag_raise.assert_called_once_with(42)
        fake.canvas.coords.assert_called_with(42, 736, 15)


class SurfaceFocusTests(unittest.TestCase):
    def test_surface_focus_uses_coarse_media_gate_without_exposing_metadata(self):
        from okabebot.surfaces import surface_focus

        for key, value in [
            ("music", {"is_playing": True}),
            ("tv", {"player_state": "BUFFERING"}),
            ("media", {"state": "playing"}),
        ]:
            result = surface_focus(
                {
                    "focus": {"active": True, "ends_at": 123},
                    key: {**value, "title": "private title"},
                }
            )
            self.assertFalse(result["ambient_allowed"])
            self.assertNotIn("private title", str(result))
        self.assertFalse(surface_focus({"deployments": [{"active": True}]})["ambient_allowed"])
        self.assertTrue(surface_focus({"media": {"state": "paused"}})["ambient_allowed"])

"""A new directory is sufficient for character discovery and public interfaces."""

import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from okabebot import characters


class CharacterRegistryTests(unittest.TestCase):
    def test_new_directory_implements_all_interfaces_without_global_registration(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "invented"
            shutil.copytree(
                Path("okabebot/characters/pip"),
                folder,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            definition = json.loads((folder / "character.json").read_text())
            definition.update(id="invented", name="Invented companion")
            (folder / "character.json").write_text(json.dumps(definition))
            importlib.invalidate_caches()
            try:
                with patch.object(characters, "__path__", list(characters.__path__) + [temp]):
                    characters.registry.cache_clear()
                    value = characters.get("invented")
                    self.assertIsInstance(value, characters.Character)
                    self.assertEqual(value.profile()["style"], "invented")
                    self.assertTrue(value.prompt("persona"))
                    self.assertTrue(value.voice()["reference_key"])
                    self.assertTrue(value.scenes())
                    self.assertEqual(value.render().size, (480, 320))
                    self.assertIn("avatar", value.assets())
                    self.assertIn("invented", characters.motion_catalog()["definitions"])
            finally:
                sys.modules.pop("okabebot.characters.invented.art", None)
                sys.modules.pop("okabebot.characters.invented", None)
                characters.registry.cache_clear()

    def test_only_golden_characters_advertise_anchored_work_poses(self):
        for name, value in characters.registry().items():
            self.assertEqual(value.supports("workbench"), name in ("okabe", "kurisu"))
            assets = value.assets()
            self.assertEqual(len(assets["frames"]), 6)
            self.assertTrue(assets["avatar"]["body"])
            if value.supports("workbench"):
                self.assertEqual(value.motion()["work_stages"]["researching"], "computer")
                self.assertEqual(value.motion()["work_stages"]["drafting"], "write")

    def test_pencil_and_keyboard_poses_keep_desk_fixed_while_hands_change(self):
        from pi import scene

        for name in ("okabe", "kurisu"):
            for stage in ("researching", "drafting"):
                first = scene.shapes(
                    style=name, work={"stage": stage, "elapsed_seconds": 1.2}, phase=1
                )
                second = scene.shapes(
                    style=name, work={"stage": stage, "elapsed_seconds": 1.5}, phase=1.6
                )

                def desks(shapes):
                    return [s for s in shapes if s[2] in ("#8a6854", "#4e4141")]

                self.assertEqual(desks(first), desks(second))
                self.assertTrue(desks(first))
                self.assertNotEqual(first, second)

    def test_gaze_tracks_pencil_and_glances_down_at_keyboard(self):
        from pi.animation import sample

        data = characters.motion_catalog()
        for name in ("okabe", "kurisu"):
            a = sample(data, name, 1, stage="drafting")
            b = sample(data, name, 1.6, stage="drafting")
            self.assertGreater(a["hand"], b["hand"])
            self.assertGreater(a["gaze"], b["gaze"])
            self.assertEqual(a["gaze_y"], 1)
            self.assertEqual(sample(data, name, 1, stage="researching")["gaze_y"], 0)
            self.assertEqual(sample(data, name, 1.7, stage="researching")["gaze_y"], 1)
            self.assertEqual(sample(data, name, 2.5, stage="researching")["gaze_y"], 0)

    def test_shoulder_elbow_and_wrist_are_one_connected_pixel_component(self):
        from PIL import Image, ImageDraw
        from okabebot.characters.workbench import draw

        colors = {"#111111", "#222222", "#333333"}
        for pose in ("write", "computer"):
            for weight in (0, 0.2, 0.5, 0.8, 1):
                for stroke in (0, 1, 2):
                    shapes = []
                    draw(
                        shapes,
                        pose,
                        dict(pose_weight=weight, hand=stroke),
                        0,
                        "#111111",
                        "#222222",
                        "#333333",
                    )
                    image = Image.new("1", (480, 360))
                    painter = ImageDraw.Draw(image)
                    for kind, box, color, width in shapes:
                        if color in colors:
                            getattr(painter, kind)(box, fill=1)
                    for side, shoulder, rest, target in [
                        (-1, (35, 60), (35, 72), (52, 70)),
                        (1, (84, 60), (84, 72), (66 + stroke, 70)),
                    ]:
                        if pose == "computer":
                            target = (53, 69 + stroke) if side < 0 else (65, 70 - stroke)
                        wrist = tuple(round(a + (b - a) * weight) * 4 for a, b in zip(rest, target))
                        start = (shoulder[0] * 4, shoulder[1] * 4)
                        pending = [start]
                        seen = {start}
                        while pending and wrist not in seen:
                            x, y = pending.pop()
                            for point in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                                if (
                                    0 <= point[0] < 480
                                    and 0 <= point[1] < 360
                                    and point not in seen
                                    and image.getpixel(point)
                                ):
                                    seen.add(point)
                                    pending.append(point)
                        self.assertIn(wrist, seen, (pose, weight, stroke, side))

    def test_voice_reference_lookup_uses_the_character_interface(self):
        from okabebot.speech import reference_key

        with patch.object(
            characters.get("okabe"),
            "voice",
            return_value={"default_voice": "calm", "reference_key": "invented-private-key"},
        ):
            self.assertEqual(reference_key("okabe"), "invented-private-key")
        self.assertEqual(reference_key("unsupported-fixture"), "unsupported-fixture")

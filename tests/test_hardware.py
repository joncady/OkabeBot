import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pi"))
from presses import PressController
from okabebot import rendering


class PressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "presses.sqlite3"
        self.bot = Mock()
        self.bot.command.return_value = {"outcome": "confirmed"}
        self.controller = PressController(self.db, self.bot)

    def test_duplicate_survives_restart(self):
        self.controller.press("test-request-001")
        restarted = PressController(self.db, self.bot)
        self.assertTrue(restarted.press("test-request-001")["deduplicated"])
        self.bot.command.assert_called_once_with("570100")

    def test_ambiguous_result_is_not_retried(self):
        self.bot.command.side_effect = RuntimeError("lost connection")
        self.assertEqual(self.controller.press("test-unknown-001")["outcome"], "unknown")
        self.assertTrue(self.controller.press("test-unknown-001")["deduplicated"])
        self.bot.command.assert_called_once()

    def test_pending_crash_record_blocks_repeat(self):
        with sqlite3.connect(self.db) as db:
            db.execute(
                "INSERT INTO presses VALUES (?, ?, ?)",
                ("test-crash-001", json.dumps({"outcome": "unknown"}), 0),
            )
        self.assertEqual(self.controller.press("test-crash-001")["outcome"], "unknown")
        self.bot.command.assert_not_called()

    def test_cooldown_and_validation_do_not_actuate(self):
        with self.assertRaises(ValueError):
            self.controller.press("")
        self.controller.press("test-first-001")
        self.assertEqual(self.controller.press("test-second-001")["outcome"], "not_sent")
        self.bot.command.assert_called_once()


class RenderingTests(unittest.TestCase):
    def test_large_text_rejected(self):
        with self.assertRaises(ValueError):
            rendering.message("many words " * 150)

    def test_long_word_wraps_within_width(self):
        from PIL import ImageDraw, Image

        f = rendering.font(24)
        lines = rendering.wrap("a" * 90, f, 432)
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(draw.textlength(line, font=f) <= 432 for line in lines))

    def test_all_themes_render(self):
        for theme in rendering.THEMES:
            self.assertEqual(
                rendering.message("Ready to go.", "Hardware lab", theme).size, (480, 320)
            )


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import tempfile
import unittest

from okabebot.timing import append_turn, recent_turns


class TimingHistoryTests(unittest.TestCase):
    def test_durable_bounded_history_and_replaced_clip(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            self.assertEqual(recent_turns(folder), [])
            for i in range(205):
                append_turn(folder, str(i), {"model_s": i / 100})
            import sqlite3

            with sqlite3.connect(folder / "turn-timings.sqlite3") as db:
                self.assertEqual(db.execute("SELECT count(*) FROM turns").fetchone()[0], 200)
            self.assertEqual(len(recent_turns(folder, 1000)), 50)
            append_turn(folder, "204", {"model_s": 9})
            self.assertEqual(recent_turns(folder, 1), [{"clip_id": "204", "model_s": 9}])

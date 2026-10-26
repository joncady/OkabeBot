import tempfile
import unittest
from okabebot.focus import FocusTimer
from okabebot.notifications import Inbox


class FocusTests(unittest.TestCase):
    def test_restart_replace_cancel_and_due(self):
        with tempfile.TemporaryDirectory() as folder:
            inbox = Inbox(folder)
            timer = FocusTimer(inbox)
            a = timer.start(25)
            self.assertEqual(FocusTimer(Inbox(folder)).status(), a)
            b = timer.start(5)
            self.assertNotEqual(a["id"], b["id"])
            self.assertIsNone(inbox.claim(now=b["ends_at"] - 1))
            self.assertEqual(inbox.claim(now=b["ends_at"])["id"], b["id"])
            timer.start(5)
            timer.cancel()
            self.assertFalse(timer.status()["active"])

    def test_invalid_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            timer = FocusTimer(Inbox(folder))
            for value in (True, 0, 181, "25", 1.5):
                with self.assertRaises(ValueError):
                    timer.start(value)

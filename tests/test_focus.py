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

    def test_expired_countdown_stops_even_when_completion_is_still_pending(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as folder:
            timer = FocusTimer(Inbox(folder))
            with patch("okabebot.focus.time.time", return_value=1000):
                status = timer.start(1)
            with patch("okabebot.focus.time.time", return_value=status["ends_at"]):
                self.assertFalse(timer.status()["active"])
            with timer.inbox.connect() as db:
                self.assertEqual(
                    "pending", db.execute("SELECT status FROM notifications").fetchone()[0]
                )

    def test_visual_projection_syncs_changes_and_pi_restart_without_replaying_audio(self):
        from unittest.mock import Mock
        from okabebot.focus import FocusProjection

        timer = Mock()
        timer.status.return_value = {"active": True, "ends_at": 5000, "id": "invented"}
        send = Mock(return_value={"active": True})
        projection = FocusProjection(timer, send)
        self.assertTrue(projection.sync("pi-session-a"))
        self.assertFalse(projection.sync("pi-session-a"))
        self.assertTrue(projection.sync("pi-session-b"))
        timer.status.return_value = {"active": False, "ends_at": None, "id": None}
        self.assertTrue(projection.sync("pi-session-b"))
        self.assertEqual(3, send.call_count)
        self.assertEqual({"active": False, "ends_at": None, "id": None}, send.call_args.args[0])

    def test_visual_failure_is_retryable_and_does_not_consume_a_change(self):
        from unittest.mock import Mock
        from okabebot.focus import FocusProjection

        timer = Mock()
        timer.status.return_value = {"active": True, "ends_at": 5000, "id": "invented"}
        send = Mock(side_effect=[{"error": "old renderer"}, {"active": True}])
        projection = FocusProjection(timer, send)
        self.assertFalse(projection.sync("pi-session"))
        self.assertEqual("unavailable", projection.health["state"])
        self.assertTrue(projection.sync("pi-session"))
        self.assertEqual("ready", projection.health["state"])

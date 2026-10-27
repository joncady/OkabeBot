import tempfile
import unittest
from unittest.mock import patch
from okabebot.arrival import queue_greeting
from okabebot.notifications import Inbox
from okabebot.notification_policy import NotificationPolicy


class ArrivalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.inbox = Inbox(self.temp.name)
        self.policy = NotificationPolicy(self.temp.name)

    def test_important_absence_summary_quip_and_durable_deduplication(self):
        with patch("okabebot.notifications.time.time", return_value=1500):
            self.inbox.publish("github", "Build failed", priority="important")
            self.inbox.publish("github", "Not important", priority="normal")
        with patch("okabebot.notifications.time.time", return_value=500):
            self.inbox.publish("github", "Before leaving", priority="urgent")
        with (
            patch("okabebot.arrival.time.time", return_value=2001),
            patch("okabebot.arrival.current_character", return_value={"style": "kurisu"}),
        ):
            result = queue_greeting(self.inbox, self.policy, 1000, 2000)
            again = queue_greeting(self.inbox, self.policy, 1000, 2000)
        self.assertEqual(result["id"], again["id"])
        self.assertIn("adult supervision", result["body"])
        self.assertIn("Build failed", result["body"])
        self.assertNotIn("Not important", result["body"])
        self.assertNotIn("Before leaving", result["body"])
        self.assertLessEqual(len(result["body"]), 500)

    def test_unavailable_sources_not_summarized_and_quiet_hours_respected(self):
        self.policy.update({"sources": {"github": {"enabled": False, "audio": "default"}}})
        with patch("okabebot.notifications.time.time", return_value=1500):
            self.inbox.publish("github", "Private update", priority="important")
        with patch("okabebot.arrival.time.time", return_value=2001):
            result = queue_greeting(self.inbox, self.policy, 1000, 2000)
        self.assertNotIn("Private update", result["body"])
        self.assertIn("No important updates were recorded", result["body"])
        with patch.object(self.policy, "quiet", return_value=True):
            self.assertEqual(self.policy.audio(result), "silent")

    def test_invalid_or_stale_arrivals_rejected(self):
        with patch("okabebot.arrival.time.time", return_value=2000):
            for away, arrived in [
                (True, 2000),
                (float("nan"), 2000),
                (1000, 1500),
                (1990, 2000),
                (1000, 2100),
            ]:
                with self.subTest(away=away, arrived=arrived), self.assertRaises(ValueError):
                    queue_greeting(self.inbox, self.policy, away, arrived)
        self.assertEqual(self.inbox.items(), [])

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
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

    def test_important_absence_recap_and_durable_deduplication(self):
        with patch("okabebot.notifications.time.time", return_value=1500):
            self.inbox.publish("github", "Build failed", priority="important")
            self.inbox.publish("github", "Not important", priority="normal")
        with patch("okabebot.notifications.time.time", return_value=500):
            self.inbox.publish("github", "Before leaving", priority="urgent")
        with patch("okabebot.arrival.time.time", return_value=2001):
            result = queue_greeting(self.inbox, self.policy, 1000, 2000)
            again = queue_greeting(self.inbox, self.policy, 1000, 2000)
        self.assertEqual(result["id"], again["id"])
        self.assertTrue(result["body"].startswith("While you were away:"))
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

    def test_door_fallback_daily_window_and_overlap_with_presence(self):
        with patch("okabebot.notifications.time.time", return_value=1500):
            self.inbox.publish("github", "Build failed", priority="important")
        with patch("okabebot.arrival.time.time", return_value=2001):
            result = queue_greeting(
                self.inbox,
                self.policy,
                arrived_at=2000,
                trigger="door_after_time",
                recap_since=1000,
            )
            overlap = queue_greeting(self.inbox, self.policy, 1000, 2000)
        self.assertEqual(result["id"], overlap["id"])
        self.assertIn("Today's important updates: Build failed", result["body"])
        self.assertNotIn("while you were away", result["body"].lower())
        # Same day remains deduplicated even outside the short overlap window.
        with patch("okabebot.arrival.time.time", return_value=2401):
            again = queue_greeting(
                self.inbox,
                self.policy,
                arrived_at=2400,
                trigger="door_after_time",
                recap_since=1000,
            )
        self.assertEqual(result["id"], again["id"])

    def test_invalid_fallback_windows_and_unknown_modes_rejected(self):
        with patch("okabebot.arrival.time.time", return_value=100000):
            for options in [
                {"trigger": "other", "recap_since": 99000},
                {"trigger": "door_after_time", "recap_since": 0},
                {"trigger": "door_after_time", "recap_since": 100001},
                {"trigger": "door_after_time", "recap_since": True},
                {"trigger": "door_after_time", "recap_since": 99000, "away_since": 99000},
            ]:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    queue_greeting(self.inbox, self.policy, arrived_at=100000, **options)

    def test_concurrent_presence_and_door_only_queue_one_welcome(self):
        with patch("okabebot.arrival.time.time", return_value=2001):
            with ThreadPoolExecutor(max_workers=2) as pool:
                presence = pool.submit(queue_greeting, self.inbox, self.policy, 1000, 2000)
                door = pool.submit(
                    queue_greeting,
                    self.inbox,
                    self.policy,
                    arrived_at=2000,
                    trigger="door_after_time",
                    recap_since=1000,
                )
                self.assertEqual(presence.result()["id"], door.result()["id"])
        self.assertEqual(len(self.inbox.items()), 1)

    def test_ble_presence_uses_same_bounded_recap_and_quiet_policy(self):
        with patch("okabebot.arrival.time.time", return_value=2000):
            result = queue_greeting(self.inbox, self.policy, 1000, 2000, trigger="ble_presence")
        self.assertIn("while you were away", result["body"])
        with patch.object(self.policy, "quiet", return_value=True):
            self.assertEqual(self.policy.audio(result), "silent")

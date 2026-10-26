import datetime as dt
import tempfile
import time
import unittest
from unittest.mock import patch

from okabebot.bridge import Bridge
from okabebot.notification_policy import NotificationPolicy
from okabebot.notifications import Inbox


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.policy = NotificationPolicy(self.tmp.name)
        self.item = {"source": "github", "priority": "important", "audio": "default"}

    def test_quiet_hours_cross_midnight_timezone_and_end_boundary(self):
        self.policy.update({"quiet_hours": {"enabled": True, "timezone": "UTC"}})
        for hour, expected in ((21, False), (22, True), (0, True), (7, True), (8, False)):
            stamp = dt.datetime(2026, 10, 25, hour, tzinfo=dt.timezone.utc).timestamp()
            self.assertEqual(self.policy.quiet(stamp), expected)
            self.assertEqual(
                self.policy.audio(self.item, stamp), "silent" if expected else "speech"
            )

    def test_silent_contract_and_source_overrides(self):
        for mode in ("silent", "chime", "speech", "default"):
            self.policy.update({"sources": {"github": {"enabled": True, "audio": mode}}})
            self.assertEqual(self.policy.audio(dict(self.item, audio="silent")), "silent")
        self.policy.update({"sources": {"github": {"enabled": False, "audio": "chime"}}})
        self.assertFalse(self.policy.enabled("github"))
        self.assertTrue(self.policy.enabled("calendar"))
        self.assertEqual(self.policy.audio(self.item), "chime")

    def test_invalid_change_is_atomic_and_preferences_survive_restart(self):
        self.policy.update({"snoozed_until": time.time() + 900})
        for change in (
            {"quiet_hours": {"start": "25:00"}},
            {"quiet_hours": {"timezone": "Bogus/Zone"}},
            {"sources": {"github": {"enabled": "yes", "audio": "speech"}}},
            {"snoozed_until": float("nan")},
            {"arbitrary": 1},
        ):
            with self.assertRaises(ValueError):
                self.policy.update(change)
        other = NotificationPolicy(self.tmp.name)
        self.assertTrue(other.snapshot()["snoozed"])
        self.assertEqual(other.settings["quiet_hours"]["start"], "22:00")

    def test_snooze_defers_delivery_and_disabled_source_is_suppressed(self):
        bridge = Bridge.__new__(Bridge)
        bridge.notification_policy = self.policy
        bridge.inbox = Inbox(self.tmp.name)
        bridge.active_notification = None
        bridge.pi = lambda _: {}
        bridge.inbox.publish("github", "Failed check", priority="important")
        self.policy.update({"snoozed_until": time.time() + 60})
        with patch("okabebot.bridge.scene.present") as present:
            bridge.deliver_notification()
            present.assert_not_called()
        self.assertEqual(bridge.inbox.items()[0]["status"], "pending")
        self.policy.update(
            {"snoozed_until": 0, "sources": {"github": {"enabled": False, "audio": "default"}}}
        )
        bridge.deliver_notification()
        self.assertEqual(bridge.inbox.items()[0]["status"], "suppressed")

    def test_quiet_delivery_still_shows_card_without_audio(self):
        bridge = Bridge.__new__(Bridge)
        bridge.notification_policy = self.policy
        bridge.inbox = Inbox(self.tmp.name)
        bridge.active_notification = None
        bridge.inbox.publish("github", "Failed check", priority="urgent", audio="chime")
        with (
            patch.object(self.policy, "quiet", return_value=True),
            patch("okabebot.bridge.scene.present") as present,
            patch("okabebot.chime.play") as chime,
            patch("okabebot.bridge.character_tools.speak") as speak,
        ):
            bridge.deliver_notification()
            present.assert_called_once()
            chime.assert_not_called()
            speak.assert_not_called()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from okabebot.notifications import Inbox
from okabebot.notification_policy import NotificationPolicy
from okabebot.bridge import Bridge


class SenderRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.policy = NotificationPolicy(self.tmp.name)
        self.inbox = Inbox(self.tmp.name, group_window_seconds=0)

    def test_legacy_preferences_migrate_without_changing_existing_rules(self):
        original = self.policy.snapshot()
        original = {
            k: v for k, v in original.items() if k in ("quiet_hours", "snoozed_until", "sources")
        }
        original["sources"] = {"github": {"enabled": True, "audio": "chime"}}
        Path(self.tmp.name, "notification-policy.json").write_text(json.dumps(original))
        policy = NotificationPolicy(self.tmp.name)
        self.assertEqual(policy.settings["sources"], original["sources"])
        self.assertEqual(policy.settings["senders"], [])

    def test_literal_source_scoping_priority_and_order_survive_reopen(self):
        self.policy.set_sender("github", "octocat", priority="urgent", audio="speech")
        self.inbox.publish("github", "Normal", priority="normal")
        item = self.inbox.publish("github", "Important sender", sender_id="octocat")
        other = self.inbox.publish("calendar", "Same ID different source", sender_id="octocat")
        self.assertEqual(item["priority"], "urgent")
        self.assertEqual(other["priority"], "normal")
        self.assertEqual(Inbox(self.tmp.name, 0).claim()["id"], item["id"])
        self.assertEqual(NotificationPolicy(self.tmp.name).audio(item), "speech")
        self.assertEqual(self.policy.sender_rule(dict(item, sender_id="Octocat")), {})

    def test_source_disable_quiet_and_explicit_audio_are_authoritative(self):
        self.policy.set_sender("github", "octocat", audio="speech", priority="urgent")
        item = self.inbox.publish("github", "News", sender_id="octocat", audio="silent")
        self.assertEqual(self.policy.audio(item), "silent")
        self.assertEqual(self.policy.audio(dict(item, audio="chime")), "chime")
        with patch.object(self.policy, "quiet", return_value=True):
            self.assertEqual(self.policy.audio(dict(item, audio="default")), "silent")
        self.policy.update({"sources": {"github": {"enabled": False, "audio": "default"}}})
        self.assertFalse(self.policy.enabled_item(item))

    def test_disabled_sender_suppresses_delivery_without_audio(self):
        self.policy.set_sender("github", "bot", enabled=False)
        self.inbox.publish("github", "Build", sender_id="bot", priority="important")
        b = Bridge.__new__(Bridge)
        b.inbox = self.inbox
        b.notification_policy = self.policy
        b.active_notification = None
        with (
            patch("okabebot.bridge.scene.present") as present,
            patch("okabebot.bridge.character_tools.speak") as speak,
        ):
            b.deliver_notification()
            present.assert_not_called()
            speak.assert_not_called()
        self.assertEqual(self.inbox.items()[0]["status"], "suppressed")

    def test_groups_never_mix_senders_with_different_rules(self):
        inbox = Inbox(self.tmp.name, group_window_seconds=3)
        self.policy.set_sender("github", "a", audio="silent")
        with patch("okabebot.notifications.time.time", return_value=1000):
            inbox.publish("github", "A", sender_id="a", group_key="repo")
            inbox.publish("github", "B", sender_id="b", group_key="repo")
        first = inbox.claim(1004)
        second = inbox.claim(1004)
        self.assertNotEqual(first["sender_id"], second["sender_id"])
        self.assertNotIn("member_ids", first)

    def test_invalid_rules_metadata_and_duplicate_ids_rejected(self):
        for identity in ["", " a ", "x\ny", "x" * 161]:
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.policy.set_sender("github", identity)
        with self.assertRaises(ValueError):
            self.inbox.publish("github", "News", sender_label="No identity")
        rule = {
            "source": "github",
            "sender_id": "x",
            "enabled": True,
            "audio": "default",
            "priority": "default",
        }
        with self.assertRaises(ValueError):
            self.policy.update({"senders": [rule, rule]})

    def test_delete_preserves_other_senders_and_priority_only_changes_future_items(self):
        first = self.inbox.publish("github", "Old", sender_id="x")
        self.policy.set_sender("github", "x", priority="important")
        self.policy.set_sender("github", "y", audio="silent")
        self.assertEqual(first["priority"], "normal")
        self.assertEqual(
            self.inbox.publish("github", "New", sender_id="x")["priority"], "important"
        )
        self.policy.delete_sender("github", "x")
        self.assertEqual([r["sender_id"] for r in self.policy.settings["senders"]], ["y"])

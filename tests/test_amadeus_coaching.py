import tempfile
import unittest

from okabebot.amadeus import Store
from okabebot.amadeus_coaching import Coaching


class CoachingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.now = 2000000000
        self.store = Store(self.folder.name, clock=lambda: self.now)
        self.coaching = Coaching(self.store, timezone="America/Los_Angeles")
        self.context = dict(
            opportunity=True,
            available=True,
            private_surface=True,
            identity_confirmed=True,
            quiet=False,
        )

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def enable(self):
        self.coaching.configure("person-a", choice="choose_topics", topics=["movement", "rest"])

    def test_no_default_opt_in_and_decline_does_not_keep_prompting(self):
        self.assertIsNotNone(self.coaching.invitation("person-a"))
        self.assertFalse(self.coaching.plan("person-a", "movement", **self.context)["allowed"])
        self.coaching.configure("person-a", choice="no")
        self.assertIsNone(self.coaching.invitation("person-a"))
        self.assertFalse(self.coaching.plan("person-a", "movement", **self.context)["allowed"])

    def test_topic_opt_in_and_context_are_required_and_output_is_quiet(self):
        self.enable()
        self.assertFalse(self.coaching.plan("person-a", "hydration", **self.context)["allowed"])
        for field in self.context:
            context = dict(self.context, **{field: field == "quiet"})
            self.assertFalse(self.coaching.plan("person-a", "movement", **context)["allowed"])
        result = self.coaching.plan("person-a", "movement", **self.context)
        self.assertTrue(result["allowed"])
        self.assertFalse(result["speech"])
        self.assertEqual(result["presentation"], "quiet_card")
        self.assertFalse(self.coaching.plan("person-b", "movement", **self.context)["allowed"])

    def test_acknowledged_delivery_limits_topics_together_and_survives_restart(self):
        self.enable()
        self.coaching.plan("person-a", "movement", **self.context)
        self.assertTrue(self.coaching.plan("person-a", "movement", **self.context)["allowed"])
        self.coaching.record_delivery("person-a", "movement")
        self.assertFalse(self.coaching.plan("person-a", "rest", **self.context)["allowed"])
        self.store.close()
        self.store = Store(self.folder.name, clock=lambda: self.now)
        self.coaching = Coaching(self.store, timezone="America/Los_Angeles")
        self.assertFalse(self.coaching.plan("person-a", "rest", **self.context)["allowed"])
        self.now += 86400
        self.assertTrue(self.coaching.plan("person-a", "rest", **self.context)["allowed"])

    def test_feedback_suppresses_without_escalation_and_stop_is_durable(self):
        self.enable()
        before = self.coaching.feedback("person-a", "helpful")
        self.assertEqual(before["topics"], ["movement", "rest"])
        self.coaching.feedback("person-a", "later")
        self.assertFalse(self.coaching.plan("person-a", "movement", **self.context)["allowed"])
        self.now += 86401
        self.coaching.feedback("person-a", "topic_off", topic="movement")
        self.assertFalse(self.coaching.plan("person-a", "movement", **self.context)["allowed"])
        self.assertTrue(self.coaching.plan("person-a", "rest", **self.context)["allowed"])
        self.coaching.feedback("person-a", "stop")
        self.assertFalse(self.coaching.plan("person-a", "rest", **self.context)["allowed"])
        with self.assertRaises(ValueError):
            self.coaching.feedback("person-a", "sounds_happy")

    def test_forget_removes_consent_and_delivery_state(self):
        self.enable()
        self.coaching.record_delivery("person-a", "movement")
        self.store.forget("person-a")
        self.assertFalse(self.coaching.plan("person-a", "movement", **self.context)["allowed"])
        self.assertIsNotNone(self.coaching.invitation("person-a"))

    def test_malformed_consent_never_enables_coaching(self):
        self.store.remember("person-a", "health.coaching", {"version": 1, "enabled": True})
        self.assertFalse(self.coaching.plan("person-a", "movement", **self.context)["allowed"])
        with self.assertRaises(ValueError):
            self.coaching.feedback("person-a", "helpful")

    def test_cooldown_crosses_local_midnight_and_missing_feedback_does_not_escalate(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        self.now = datetime(2030, 1, 1, 23, 59, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
        self.enable()
        self.coaching.record_delivery("person-a", "movement")
        self.now += 120
        self.assertEqual(
            self.coaching.plan("person-a", "rest", **self.context)["reason"], "cooldown"
        )
        self.now += 3600
        self.assertTrue(self.coaching.plan("person-a", "rest", **self.context)["allowed"])

    def test_negative_feedback_pauses_and_declining_later_does_not_reprompt(self):
        self.coaching.configure("person-a", choice="not_now")
        self.assertIsNone(self.coaching.invitation("person-a"))
        self.enable()
        self.coaching.feedback("person-a", "not_helpful")
        self.assertEqual(self.coaching.plan("person-a", "rest", **self.context)["reason"], "paused")
        with self.assertRaises(ValueError):
            self.coaching.configure("person-a", choice="choose_topics", topics=[])

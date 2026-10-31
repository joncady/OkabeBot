"""Invented preferences only; no household data, model calls or speech."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from okabebot.amadeus_live import ProactiveConversation
from okabebot.amadeus_conversation import PreferenceConversation, opening_preferences, RECENCY_KEY
from okabebot.amadeus_habits import preference
from okabebot.amadeus_onboarding import SYSTEM, KEY


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1900000000
        self.live = ProactiveConversation(Path(self.tmp.name), lambda: self.now)
        with self.live.store() as s:
            s.remember(
                SYSTEM,
                KEY,
                {
                    "profile": "fiction",
                    "sources": ["door_presence"],
                    "paused": False,
                    "guest": False,
                    "timezone": "UTC",
                },
            )
        self.live.configure(enabled=True, destination="desk")

    def save(self, field, values):
        with self.live.store() as s:
            PreferenceConversation(s).confirm(
                "fiction", field, values, scope="usually", confirmed=True, operation="append"
            )

    def test_recent_interest_excluded_from_opener_but_retained_for_user_queries(self):
        self.save("genres", ["invented mysteries"])
        self.now += 25 * 3600
        self.save("interests", ["invented astronomy"])
        composer = Mock(return_value={"reply": "An optional fresh angle", "memory": None})
        self.live.opening({"kind": "checkin"}, composer)
        self.assertNotIn("interests", composer.call_args.args[1]["preferences"])
        self.assertEqual(
            composer.call_args.args[1]["preferences"]["media"]["genres"], ["invented mysteries"]
        )
        with self.live.store() as s:
            self.assertEqual(
                preference(s, "fiction", "context.preferences")["interests"], ["invented astronomy"]
            )
        self.now += 24 * 3600
        self.live.opening({"kind": "checkin"}, composer)
        self.assertIn("interests", composer.call_args.args[1]["preferences"])

    def test_only_fresh_context_does_not_generate_or_consume_a_question(self):
        self.save("interests", ["invented paper craft"])
        composer = Mock()
        result = self.live.opening({}, composer)
        self.assertEqual(result, {"reply": "", "memory": None})
        composer.assert_not_called()
        with self.live.store() as s:
            self.assertEqual(preference(s, "fiction", "conversation.invitation_budget")["count"], 0)

    def test_legacy_last_memory_timestamp_is_conservative_per_field(self):
        with self.live.store() as s:
            s.remember(
                "fiction",
                "context.preferences",
                {"interests": ["invented stars"], "media": {"genres": ["invented adventure"]}},
            )
            s.remember(
                "fiction",
                "conversation.last_memory",
                {"field": "interests", "provenance": "user_confirmed"},
            )
            prefs, excluded = opening_preferences(s, "fiction", now=self.now, cooldown_hours=24)
            self.assertEqual(excluded, ["interests"])
            self.assertIn("media", prefs)

    def test_dashboard_setting_preserves_opt_in_and_can_disable_cooldown(self):
        self.save("interests", ["invented maps"])
        settings = self.live.configure(enabled=True, destination="desk", topic_cooldown_hours=0)
        self.assertEqual(settings["topic_cooldown_hours"], 0)
        composer = Mock(return_value={"reply": "A new angle", "memory": None})
        self.live.opening({}, composer)
        self.assertIn("interests", composer.call_args.args[1]["preferences"])
        for invalid in (-1, 169, True, 1.5):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                self.live.configure(enabled=True, destination="desk", topic_cooldown_hours=invalid)
        with self.live.store() as s:
            recent = preference(s, "fiction", RECENCY_KEY)
            self.assertEqual(recent, {"interests": self.now})

    def test_forgetting_preferences_removes_recency_and_legacy_metadata(self):
        from okabebot.amadeus_onboarding import Onboarding

        self.save("interests", ["invented origami"])
        service = Onboarding(Path(self.tmp.name))
        try:
            service.forget({"key": "context.preferences"})
            with self.live.store() as s:
                self.assertEqual(preference(s, "fiction", RECENCY_KEY, {}), {})
                self.assertEqual(preference(s, "fiction", "conversation.last_memory", {}), {})
        finally:
            service.store.close()

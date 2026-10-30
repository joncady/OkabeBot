"""Invented conversation learning, boundaries and downstream recommendation regression."""

import tempfile
import unittest
from pathlib import Path
from okabebot.amadeus import Store
from okabebot.amadeus_onboarding import SYSTEM, KEY
from okabebot.amadeus_habits import preference
from okabebot.amadeus_conversation import PreferenceConversation


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name), sources=[], clock=lambda: 1900000000)
        self.addCleanup(self.store.close)
        self.store.remember(
            SYSTEM, KEY, dict(profile="fiction", paused=False, guest=False, timezone="UTC")
        )
        self.store.remember("fiction", "conversation.preferences", dict(enabled=True, speech=False))
        self.store.remember(
            "fiction", "context.preferences", {"media": {"providers": ["Invented"]}}
        )
        self.policy = PreferenceConversation(self.store)
        self.window = dict(
            requested=True,
            available=True,
            identity_confirmed=True,
            private_surface=True,
            media_playing=False,
            quiet=False,
        )

    def test_protected_windows_and_ack_budget(self):
        for key, value in (("quiet", True), ("media_playing", True), ("identity_confirmed", False)):
            self.assertFalse(
                self.policy.offer("fiction", "entertainment", **(self.window | {key: value}))[
                    "allowed"
                ]
            )
        offer = self.policy.offer("fiction", "entertainment", **self.window)
        self.assertTrue(offer["allowed"])
        self.assertFalse(offer["speech"])
        self.assertTrue(self.policy.offer("fiction", "entertainment", **self.window)["allowed"])
        self.policy.delivered("fiction", offer)
        self.assertEqual(
            self.policy.offer("fiction", "entertainment", **self.window)["reason"], "daily_limit"
        )

    def test_tonight_is_not_a_persistent_dislike(self):
        result = self.policy.confirm(
            "fiction", "avoid", ["horror"], scope="this_conversation", confirmed=True
        )
        self.assertFalse(result["stored"])
        self.assertNotIn("avoid", preference(self.store, "fiction", "context.preferences")["media"])

    def test_confirmed_learning_preserves_other_fields(self):
        self.policy.confirm("fiction", "genres", ["mystery"], scope="usually", confirmed=True)
        prefs = preference(self.store, "fiction", "context.preferences")
        self.assertEqual(prefs["media"], {"genres": ["mystery"], "providers": ["Invented"]})
        self.policy.confirm("fiction", "hobbies", ["gardening"], scope="usually", confirmed=True)
        self.assertEqual(
            preference(self.store, "fiction", "context.preferences")["hobbies"], ["gardening"]
        )

    def test_silence_unconfirmed_and_other_identity_cannot_write(self):
        with self.assertRaises(ValueError):
            self.policy.confirm("fiction", "genres", ["mystery"], scope="usually")
        with self.assertRaises(PermissionError):
            self.policy.confirm("other", "genres", ["mystery"], scope="usually", confirmed=True)

    def test_speech_requires_two_explicit_permissions(self):
        self.assertFalse(
            self.policy.offer("fiction", "goals", speech_opt_in=True, **self.window)["speech"]
        )
        self.store.remember("fiction", "conversation.preferences", dict(enabled=True, speech=True))
        self.assertTrue(
            self.policy.offer("fiction", "goals", speech_opt_in=True, **self.window)["speech"]
        )
        self.assertFalse(self.policy.offer("fiction", "goals", **self.window)["speech"])

    def test_confirmed_answer_changes_actual_catalogue_candidates(self):
        from okabebot.amadeus_opportunities import ContextPlanner, configure_context

        catalog = [
            dict(
                id="fiction-1",
                title="The Paper Observatory",
                genres=["mystery"],
                minutes=40,
                provider="Invented",
                content_tags=[],
            )
        ]
        configure_context(self.store, "fiction", {"media": {"providers": ["Invented"]}}, catalog)
        planner = ContextPlanner(self.store)
        before = planner._choices(
            "fiction",
            preference(self.store, "fiction", "context.preferences"),
            {},
            self.store.clock(),
        )
        self.assertEqual(before, [])
        self.policy.confirm("fiction", "genres", ["mystery"], scope="usually", confirmed=True)
        after = planner._choices(
            "fiction",
            preference(self.store, "fiction", "context.preferences"),
            {},
            self.store.clock(),
        )
        self.assertEqual([item["id"] for item in after], ["fiction-1"])

"""Invented text-only preference sessions; no hardware or participant input."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from okabebot.amadeus_text import TextConversation
from okabebot.amadeus_live import STATE
from okabebot.amadeus_habits import preference
from okabebot.amadeus_onboarding import SYSTEM, KEY


class TextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.chat = TextConversation(Path(self.tmp.name), clock=lambda: 1000)
        with self.chat.store() as s:
            s.remember(SYSTEM, KEY, dict(profile="fiction", paused=False, guest=False))
            s.remember("fiction", "conversation.preferences", {"enabled": True})
            s.remember("fiction", STATE, {"pending": "voice stays intact"})
        with self.chat.store() as s:
            s.remember("fiction", "conversation.memory_policy", {"auto_accept": False})
        self.generate = Mock(
            return_value={
                "reply": "That sounds fun.",
                "memory": {"field": "hobbies", "values": ["pottery"], "evidence": "pottery"},
            }
        )

    def test_confirmation_stores_only_after_explicit_yes_and_leaves_voice_alone(self):
        result = self.chat.send("I like pottery", self.generate)
        self.assertEqual(result["pending"]["field"], "hobbies")
        with self.chat.store() as s:
            self.assertEqual(preference(s, "fiction", "context.preferences", {}), {})
        self.chat.send("yes", self.generate)
        with self.chat.store() as s:
            self.assertEqual(
                preference(s, "fiction", "context.preferences", {})["hobbies"], ["pottery"]
            )
            self.assertEqual(preference(s, "fiction", STATE, {})["pending"], "voice stays intact")
        self.assertEqual(self.generate.call_count, 1)

    def test_reset_discards_pending_and_feedback_is_private_bounded(self):
        self.chat.send("pottery", self.generate)
        self.chat.end()
        self.assertIsNone(self.chat.context())
        self.assertTrue(
            self.chat.feedback({"rating": "useful", "note": "Invented feedback"})["saved"]
        )
        self.assertEqual((Path(self.tmp.name) / "text-feedback.json").stat().st_mode & 0o777, 0o600)

    def test_setup_and_consent_required_and_input_bounded(self):
        with self.chat.store() as s:
            s.remember("fiction", "conversation.preferences", {"enabled": False})
        with self.assertRaises(ValueError):
            self.chat.send("hello", self.generate)
        for value in ("", "x" * 1001, None):
            with self.assertRaises(ValueError):
                self.chat.send(value, self.generate)
        self.generate.assert_not_called()

    def test_auto_accept_default_and_uncertainty_and_grounding(self):
        with self.chat.store() as s:
            s.remember("fiction", "conversation.memory_policy", {})
        result = self.chat.send("I enjoy pottery", self.generate)
        self.assertIsNone(result["pending"])
        self.assertEqual(result["memory"]["confidence"], 0.95)
        self.assertEqual(result["reply"], "That sounds fun.")
        result = self.chat.send("Maybe I enjoy pottery tonight", self.generate)
        self.assertIsNotNone(result["pending"])
        self.assertLess(result["pending"]["confidence"], 0.9)

    def test_confidence_never_auto_accepts_temporary_third_party_or_sensitive(self):
        from okabebot.preference_confidence import confidence

        memory = {"values": ["pottery"]}
        for text in (
            "My friend says I enjoy pottery",
            "Do I enjoy pottery?",
            "I enjoy pottery today",
            "I enjoy pottery for anxiety",
            "I used to like pottery",
            'She said "I enjoy pottery"',
        ):
            self.assertLess(confidence(text, memory), 0.9)
        self.assertLess(confidence("I enjoy pottery", {"values": ["skydiving"]}), 0.9)

    def test_calendar_tool_turn_is_silent_and_followup_keeps_context(self):
        specs = {"get_calendar_agenda": {}}
        tool = Mock(
            return_value={"reply": "No events in this view.", "tools": ["get_calendar_agenda"]}
        )
        result = self.chat.send("What is on my calendar?", self.generate, tool, specs)
        self.assertEqual(result["tools"], ["get_calendar_agenda"])
        self.generate.assert_not_called()
        self.chat.send("What about tomorrow?", self.generate, tool, specs)
        self.assertIn("calendar", tool.call_args.args[0])
        with self.chat.store() as s:
            state = preference(s, "fiction", "conversation.text", {})
            self.assertEqual(len(state["history"]), 4)
        self.chat.end()
        with self.chat.store() as s:
            self.assertEqual(preference(s, "fiction", "conversation.text", {})["history"], [])

    def test_large_unicode_history_stays_within_private_record_budget(self):
        generate = Mock(return_value={"reply": "A useful answer.", "memory": None})
        for _ in range(5):
            self.chat.send("音" * 900, generate)
        with self.chat.store() as s:
            state = preference(s, "fiction", "conversation.text", {})
            import json

            self.assertLess(len(json.dumps(state).encode()), 4096)

    def test_character_question_cannot_propose_owner_memory_and_model_gets_capabilities(self):
        generate = Mock(
            return_value={
                "reply": "A crisp apple would suit this character.",
                "memory": {"field": "food_drink", "values": ["apples"], "evidence": "apples"},
            }
        )
        result = self.chat.send(
            "Do you like apples?",
            generate,
            specs={"get_calendar_agenda": {"description": "Read calendar events"}},
        )
        self.assertIsNone(result["pending"])
        self.assertIsNone(result["memory"])
        self.assertEqual(
            generate.call_args.args[1]["capabilities"][0]["name"], "get_calendar_agenda"
        )

    def test_past_tense_question_always_reaches_shared_tool_dispatcher(self):
        tool = Mock(
            return_value={
                "reply": "The connected feed contains a notice.",
                "tools": ["get_context_feed"],
            }
        )
        result = self.chat.send(
            "Were there any transit notices today?", self.generate, tool, {"get_context_feed": {}}
        )
        tool.assert_called_once()
        self.generate.assert_not_called()
        self.assertEqual(result["tools"], ["get_context_feed"])

    def test_explicit_conversation_route_preserves_preference_policy(self):
        tool = Mock(return_value={"reply": "", "tools": [], "conversation": True})
        result = self.chat.send("I like pottery", self.generate, tool, {"get_context_feed": {}})
        tool.assert_called_once()
        self.generate.assert_called_once()
        self.assertEqual(result["pending"]["field"], "hobbies")

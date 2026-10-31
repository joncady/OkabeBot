"""Invented delivery receipts and conversational handoffs; no speech or accounts."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from okabebot.amadeus_live import ProactiveConversation, STATE
from okabebot.amadeus_suggestions import Suggestions, JOURNAL
from okabebot.amadeus_habits import preference
from okabebot.amadeus_onboarding import SYSTEM, KEY


class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1900000000
        self.live = ProactiveConversation(Path(self.tmp.name), lambda: self.now)
        self.journal = Suggestions(self.live.folder, lambda: self.now)
        with self.live.store() as s:
            s.remember(
                SYSTEM,
                KEY,
                dict(profile="fiction", paused=False, guest=False, sources=["door_presence"]),
            )
        self.live.configure(enabled=True, destination="desk", max_per_day=3, min_gap_minutes=120)
        with self.live.store() as s:
            s.remember(
                "fiction",
                STATE,
                dict(
                    consumed=True,
                    claimed_at=self.now,
                    session_until=self.now + 600,
                    turns=0,
                    invitation_kind="checkin",
                    last_reply="How has the invented garden been?",
                    history=[{"role": "assistant", "content": "How has the invented garden been?"}],
                ),
            )
            s.remember("fiction", "context.preferences", {"hobbies": ["invented gardening"]})

    def test_receipt_requires_delivery_call_and_is_stable_without_content(self):
        self.assertEqual(self.journal.explanation(), {"available": False})
        a = self.journal.record("checkin", claimed_at=self.now, topic="hobbies")
        b = self.journal.record("checkin", claimed_at=self.now, topic="hobbies")
        self.assertEqual(a["id"], b["id"])
        explanation = self.journal.explanation()["suggestion"]
        self.assertIn("connected context", explanation["reason"])
        self.assertNotIn("invented gardening", str(explanation))

    def test_feedback_is_id_bound_idempotent_and_not_a_taste_edit(self):
        a = self.journal.record("checkin", claimed_at=self.now, topic="hobbies")
        for outcome in ("too_soon", "too_soon", "good_timing", "not_interested"):
            self.journal.feedback({"suggestion_id": a["id"], "outcome": outcome})
        with self.live.store() as s:
            self.assertEqual(
                preference(s, "fiction", "context.preferences"), {"hobbies": ["invented gardening"]}
            )
            self.assertEqual(len(preference(s, "fiction", JOURNAL)["items"]), 1)
            self.assertEqual(preference(s, "fiction", "conversation.feedback_pause", {}), {})
        with self.assertRaises(ValueError):
            self.journal.feedback({"suggestion_id": "f" * 32, "outcome": "too_soon"})
        self.assertEqual(self.journal.explanation()["suggestion"]["feedback"], "not_interested")

    def test_guest_or_pause_blocks_read_and_feedback(self):
        a = self.journal.record("checkin", claimed_at=self.now, topic="hobbies")
        with self.live.store() as s:
            setup = preference(s, SYSTEM, KEY)
            setup["guest"] = True
            s.remember(SYSTEM, KEY, setup)
        with self.assertRaises(PermissionError):
            self.journal.explanation()
        with self.assertRaises(PermissionError):
            self.journal.feedback({"suggestion_id": a["id"], "outcome": "good_timing"})

    def test_tool_lookup_keeps_dialogue_and_followup_has_history(self):
        tools = Mock(
            return_value={
                "reply": "The invented meeting is at noon.",
                "tools": ["get_calendar_agenda"],
            }
        )
        generate = Mock(return_value={"reply": "That still leaves the afternoon.", "memory": None})
        answer = self.live.respond("What is on my calendar?", generate, tool_turn=tools, specs={})
        self.assertIn("noon", answer)
        self.assertIsNotNone(self.live.context())
        tools.return_value = {"conversation": True, "tools": [], "reply": ""}
        self.live.respond("That gives me a bit of time", generate, tool_turn=tools, specs={})
        history = generate.call_args.args[1]["history"]
        self.assertTrue(any("noon" in row["content"] for row in history))
        self.assertEqual(
            [r["role"] for r in self.live.context()["history"]][-4:],
            ["user", "assistant", "user", "assistant"],
        )

    def test_polite_stop_closes_without_generation_or_memory(self):
        generate = Mock()
        self.live.answer("Thanks, that's all.", generate)
        self.assertIsNone(self.live.context())
        generate.assert_not_called()

    def test_pending_confirmation_and_stop_never_route_through_tools(self):
        with self.live.store() as s:
            state = preference(s, "fiction", STATE)
            state["pending"] = {"field": "hobbies", "values": ["invented cello"]}
            s.remember("fiction", STATE, state)
        tool = Mock(side_effect=AssertionError("A confirmation must not run tools"))
        generate = Mock(side_effect=AssertionError("A confirmation must not run the model"))
        reply = self.live.respond("Sure", generate, tool_turn=tool, specs={})
        self.assertIn("keep that in mind", reply)
        self.assertIsNone(self.live.context()["pending"])
        with self.live.store() as s:
            self.assertIn(
                "invented cello", preference(s, "fiction", "context.preferences")["hobbies"]
            )
        self.live.respond("Thanks, that's all", generate, tool_turn=tool, specs={})
        self.assertIsNone(self.live.context())
        tool.assert_not_called()
        generate.assert_not_called()

    def test_closed_health_session_is_not_reinitialized_as_generic_chat(self):
        from unittest.mock import patch

        with self.live.store() as s:
            state = preference(s, "fiction", STATE)
            state["invitation_kind"] = "health"
            s.remember("fiction", STATE, state)
        generate = Mock()
        tools = Mock()
        with patch("okabebot.amadeus_health.Health.session_allowed", return_value=False):
            self.assertIsNone(
                self.live.respond("More about that", generate, tool_turn=tools, specs={})
            )
        generate.assert_not_called()
        tools.assert_not_called()
        with self.live.store() as s:
            state = preference(s, "fiction", STATE)
            self.assertEqual(state["invitation_kind"], "health")
            self.assertEqual(state["session_until"], 0)

    def test_privacy_change_during_tool_read_withholds_reply_and_continuation(self):
        def tools(*a, **kw):
            with self.live.store() as s:
                setup = preference(s, SYSTEM, KEY)
                setup["guest"] = True
                s.remember(SYSTEM, KEY, setup)
            return {"reply": "Private synthetic result", "tools": ["get_calendar_agenda"]}

        generate = Mock()
        self.assertIsNone(
            self.live.respond("Check my calendar", generate, tool_turn=tools, specs={})
        )
        generate.assert_not_called()

    def test_revising_topic_feedback_removes_only_its_own_suppression(self):
        receipt = self.journal.record("checkin", claimed_at=self.now, topic="hobbies")
        self.journal.feedback({"suggestion_id": receipt["id"], "outcome": "not_interested"})
        self.journal.feedback({"suggestion_id": receipt["id"], "outcome": "good_timing"})
        with self.live.store() as s:
            self.assertNotIn("hobbies", preference(s, "fiction", "conversation.topic_feedback", {}))

    def test_preference_forget_cannot_resurrect_a_legacy_receipt(self):
        from okabebot.amadeus_onboarding import Onboarding
        from unittest.mock import patch
        import json

        original = Path.read_text

        def read(path, *a, **kw):
            if path.name == "amadeus-conversation.json":
                return json.dumps({"state": "delivered", "updated_at": self.now + 1})
            return original(path, *a, **kw)

        with patch.object(Path, "read_text", read):
            self.assertTrue(self.journal.explanation()["available"])
            service = Onboarding(self.live.folder)
            try:
                service.forget({"key": "context.preferences"})
            finally:
                service.store.close()
            self.assertFalse(self.journal.explanation()["available"])

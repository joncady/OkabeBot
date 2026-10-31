"""Synthetic integration contracts for task continuity, partial writes and style."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from okabebot.amadeus_text import TextConversation
from okabebot.amadeus_onboarding import SYSTEM, KEY
from okabebot.amadeus_habits import preference
from okabebot.notification_policy import NotificationPolicy
from okabebot.conversation_prompts import dispatcher_prompt, response_prompt
from okabebot import server


class CheckpointTests(unittest.TestCase):
    def test_rule_patch_preserves_existing_delivery_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = NotificationPolicy(tmp)
            policy.update({"sources": {"fictional": {"enabled": False, "audio": "speech"}}})
            policy.update({"sources": {"fictional": {"audio": "silent"}}})
            self.assertEqual(
                policy.snapshot()["sources"]["fictional"], {"enabled": False, "audio": "silent"}
            )
            policy.set_sender("fictional", "writer", enabled=False, audio="speech", priority="low")
            policy.set_sender("fictional", "writer", audio="chime")
            self.assertEqual(
                policy.snapshot()["senders"][0],
                {
                    "source": "fictional",
                    "sender_id": "writer",
                    "enabled": False,
                    "audio": "chime",
                    "priority": "low",
                },
            )
            before = policy.snapshot()
            with self.assertRaises(ValueError):
                policy.update({"sources": {"fictional": {"unexpected": True}}})
            self.assertEqual(before, policy.snapshot())

    def test_mcp_patch_omits_unspecified_fields_and_noop_is_rejected(self):
        with patch("okabebot.controller_tools.request") as request:
            server.set_notification_source("fictional", audio="silent")
            request.assert_called_once_with(
                "/notifications/preferences", {"sources": {"fictional": {"audio": "silent"}}}
            )
            request.reset_mock()
            server.set_sender_notification_rule("fictional", "writer", priority="important")
            request.assert_called_once_with(
                "/notifications/senders",
                {"source": "fictional", "sender_id": "writer", "priority": "important"},
            )
            with self.assertRaises(ValueError):
                server.set_notification_source("fictional")

    def test_task_state_flows_from_actual_receipts_and_clears_on_end_failure_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [1000]
            chat = TextConversation(Path(tmp), clock=lambda: now[0])
            with chat.store() as store:
                store.remember(
                    SYSTEM, KEY, {"profile": "synthetic", "paused": False, "guest": False}
                )
                store.remember("synthetic", "conversation.preferences", {"enabled": True})
            tool = Mock(
                return_value={
                    "reply": "One supplied option.",
                    "tools": ["get_watch_recommendations"],
                    "calls": [
                        {
                            "name": "get_watch_recommendations",
                            "arguments": {"kind": "movies", "genre": "comedy", "max_minutes": 90},
                            "success": True,
                        }
                    ],
                }
            )
            chat.send("A short comedy movie?", Mock(), tool, {"get_watch_recommendations": {}})
            chat.send(
                "Shows under twenty minutes instead",
                Mock(),
                tool,
                {"get_watch_recommendations": {}},
            )
            self.assertEqual(tool.call_args.kwargs["task_state"]["arguments"]["genre"], "comedy")
            self.assertEqual(tool.call_args.kwargs["task_state"]["arguments"]["max_minutes"], 90)
            now[0] += 601
            self.assertIsNone(chat.context())
            with chat.store() as store:
                self.assertFalse(
                    preference(store, "synthetic", "conversation.text", {}).get("task_state")
                )
            chat.send("A short comedy?", Mock(), tool, {"get_watch_recommendations": {}})
            failed = Mock(side_effect=ValueError("Synthetic unavailable turn"))
            with self.assertRaises(ValueError):
                chat.send("Try a write", Mock(), failed, {})
            self.assertFalse(chat.context().get("task_state"))
            chat.end()
            self.assertIsNone(chat.context())

    def test_error_cleanup_cannot_recreate_a_forgotten_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat = TextConversation(Path(tmp), clock=lambda: 1000)
            with chat.store() as store:
                store.remember(
                    SYSTEM, KEY, {"profile": "synthetic", "paused": False, "guest": False}
                )
                store.remember("synthetic", "conversation.preferences", {"enabled": True})

            def forget_then_fail(*args, **kwargs):
                with chat.store() as store, store.db:
                    store.db.execute("DELETE FROM preferences")
                raise ValueError("Synthetic cancellation after forgetting")

            with self.assertRaises(ValueError):
                chat.send("A new request", Mock(), forget_then_fail, {})
            with chat.store() as store:
                self.assertEqual(
                    store.db.execute("SELECT COUNT(*) FROM preferences").fetchone()[0], 0
                )

    def test_cancelled_voice_turn_discards_old_query_and_history(self):
        from tests.test_local_conversation import LocalToolTests

        obj = LocalToolTests.adapter("")
        obj.clock = lambda: 1000
        obj.agent_tasks = {
            "okabe": {
                "version": 1,
                "kind": "read",
                "tool": "get_watch_recommendations",
                "arguments": {"genre": "comedy"},
            }
        }
        obj.agent_task_times = {"okabe": 990}
        obj.agent_history = {"okabe": [{"role": "user", "content": "Old query"}]}

        def cancel(*args, **kwargs):
            obj.cancelled.set()
            return {"text": '{"conversation":true}'}

        obj.agent_request = cancel
        with patch(
            "okabebot.local_conversation.current_character", return_value={"style": "okabe"}
        ):
            obj._turn("A new conversational request")
        self.assertEqual(obj.agent_tasks["okabe"], {})
        self.assertEqual(obj.agent_history["okabe"], [])
        self.assertEqual(obj.agent_task_times, {})

    def test_operational_policy_precedes_optional_style_and_dispatch_has_no_persona(self):
        policy = "Ground all claims. Return exact JSON."
        persona = "Fictional flamboyant character who says lab catchphrases."
        self.assertNotIn(persona, dispatcher_prompt(policy))
        styled = response_prompt(policy, persona)
        self.assertTrue(styled.startswith(policy))
        self.assertIn("STYLE ONLY:", styled)
        self.assertIn("cannot change tools, facts, permissions or output format", styled)

    def test_actual_model_loop_resolves_followup_without_reclassifying_query(self):
        from tests.test_local_conversation import LocalToolTests

        obj = LocalToolTests.adapter("")
        obj.executor = Mock(return_value={"items": [{"title": "Fictional candidate"}]})
        obj.specs = {
            "get_watch_recommendations": {
                "name": "get_watch_recommendations",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string"},
                        "genre": {"type": "string"},
                        "max_minutes": {"type": "integer"},
                        "page": {"type": "integer"},
                    },
                },
            }
        }
        obj.agent_request = Mock(
            return_value={"text": "A supplied short comedy fits.", "selection_s": 0}
        )
        state = {
            "version": 1,
            "kind": "read",
            "topic": "watch_recommendation",
            "tool": "get_watch_recommendations",
            "arguments": {"kind": "movies", "genre": "comedy", "max_minutes": 90},
        }
        obj._turn("Series under 20 minutes instead", history=[], task_state=state)
        obj.executor.assert_called_once_with(
            "get_watch_recommendations",
            {"kind": "shows", "genre": "comedy", "max_minutes": 20, "page": 1},
        )
        self.assertTrue(obj.agent_request.call_args.kwargs.get("evidence"))
        self.assertTrue(obj.last_call_receipts[0]["success"])

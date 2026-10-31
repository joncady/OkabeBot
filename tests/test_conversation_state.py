"""Invented conversational query continuity; no model, provider or device use."""

from copy import deepcopy
import json
import unittest

from okabebot.conversation_state import (
    MAX_STATE_BYTES,
    READ_ARGUMENTS,
    context_for_turn,
    normalize_state,
    resolve_read_followup,
    update_task_state,
)


def receipt(name, arguments, **kwargs):
    return {"name": name, "arguments": arguments, "success": True, **kwargs}


def watch_state(**arguments):
    return update_task_state(
        {},
        user_text="Recommend a documentary movie under 90 minutes",
        calls=[
            receipt(
                "get_watch_recommendations",
                {"kind": "movies", "genre": "documentary", "max_minutes": 90, **arguments},
            )
        ],
    )


class TaskStateTests(unittest.TestCase):
    def test_only_real_read_contracts_can_seed_query_state(self):
        from okabebot.local_conversation import READ_TOOLS
        from okabebot import server
        import asyncio

        self.assertLessEqual(set(READ_ARGUMENTS), READ_TOOLS)
        schemas = {tool.name: tool.inputSchema for tool in asyncio.run(server.mcp.list_tools())}
        for name, arguments in READ_ARGUMENTS.items():
            self.assertLessEqual(arguments, set(schemas[name].get("properties", {})), name)

    def test_success_receipts_preserve_query_constraints_and_source_target(self):
        state = update_task_state(
            {},
            user_text="Read current rail notices",
            calls=[
                receipt("get_context_feed", {"source": "transit", "view": "current", "offset": 0})
            ],
        )
        self.assertEqual(state["tool"], "get_context_feed")
        self.assertEqual(state["target"], {"kind": "source", "id": "transit"})
        self.assertEqual(state["constraints"], {"view": "current"})
        self.assertEqual(state["arguments"]["offset"], 0)

    def test_writes_and_failed_or_cancelled_reads_cannot_inherit_authority(self):
        prior = watch_state()
        for calls in [
            [receipt("set_speaker_volume", {"percent": 70})],
            [receipt("get_watch_recommendations", {"kind": "shows"}, success=False)],
            [receipt("get_watch_recommendations", {"kind": "shows"}, cancelled=True)],
            [receipt("get_watch_recommendations", {"kind": "shows"}, result={"error": "denied"})],
            [receipt("get_watch_recommendations", {"kind": "shows"}, result={"available": False})],
            [
                receipt("get_current_media", {}),
                receipt("move_companion", {"location_id": "invented"}),
            ],
        ]:
            with self.subTest(calls=calls):
                state = update_task_state(prior, user_text="Try that", calls=calls)
                self.assertEqual(state["kind"], "conversation")
                self.assertNotIn("arguments", state)
                self.assertIsNone(resolve_read_followup("Another one", state))
        self.assertIsNone(resolve_read_followup("Turn it up", prior))

    def test_corrected_watch_kind_and_runtime_keep_genre_without_page_carryover(self):
        state = watch_state(page=4)
        before = deepcopy(state)
        result = resolve_read_followup("Series under 20 minutes instead", state)
        self.assertEqual(
            result,
            {
                "name": "get_watch_recommendations",
                "arguments": {
                    "kind": "shows",
                    "genre": "documentary",
                    "max_minutes": 20,
                    "page": 1,
                },
            },
        )
        self.assertEqual(state, before)
        # Negated corrections return to normal routing rather than auto-querying.
        self.assertIsNone(
            resolve_read_followup("Actually, not movies, shows under 25 minutes", state)
        )

    def test_explicit_genre_corrections_and_limit_removal_do_not_invent_filters(self):
        state = watch_state()
        result = resolve_read_followup("What about sci-fi under 1.5 hours?", state)
        self.assertEqual(result["arguments"]["genre"], "science-fiction")
        self.assertEqual(result["arguments"]["max_minutes"], 90)
        result = resolve_read_followup("Actually, any genre and no time limit", state)
        self.assertNotIn("genre", result["arguments"])
        self.assertNotIn("max_minutes", result["arguments"])
        self.assertIsNone(resolve_read_followup("Actually, not documentary", state))
        self.assertIsNone(resolve_read_followup("And something longer than 100 minutes", state))
        self.assertIsNone(resolve_read_followup("What about comedy or drama?", state))
        self.assertIsNone(resolve_read_followup("Actually, under 2.75 minutes", state))

    def test_nonreferential_new_requests_do_not_receive_stale_constraints(self):
        state = watch_state()
        self.assertIsNone(resolve_read_followup("Recommend a comedy", state))
        self.assertIsNone(resolve_read_followup("And Thursday?", state))
        self.assertIsNone(resolve_read_followup("Why does ice float?", state))
        self.assertIsNone(resolve_read_followup("Why that one?", state))
        another = resolve_read_followup("Another one please", state)
        self.assertEqual(another["arguments"]["genre"], "documentary")

    def test_bare_pick_references_are_short_and_do_not_hijack_new_requests(self):
        state = watch_state()
        for text in (
            "Another one please",
            "One more pick",
            "And the same recommendation",
            "Same show please.",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    resolve_read_followup(text, state)["name"], "get_watch_recommendations"
                )
        for text in (
            "Another question: what is 2+2?",
            "One more question about comedy: why is it funny?",
            "Same question: is the garage open?",
            "Another topic, I like music",
            "Another comedy question: why do we laugh?",
            "Same drama question about the ending",
            "One more thing: is a show playing?",
            "Another recipe please",
            "One more thing: what is playing?",
            "Same scientist who discovered gravity?",
            "And is a show playing on TV?",
            "And turn the speaker volume down for another movie",
            "And do not recommend another comedy",
            "And not another comedy movie under 20 minutes",
            "And without a comedy movie under 20 minutes",
            "Actually never show another comedy",
            'And someone said "another comedy"',
            "And hypothetically a comedy under 20 minutes",
            "And if I asked for another movie",
            "And I feel unsafe during another movie",
        ):
            with self.subTest(text=text):
                self.assertIsNone(resolve_read_followup(text, state))
        calendar = update_task_state(
            {}, user_text="Calendar today", calls=[receipt("get_calendar_agenda", {"day": "today"})]
        )
        for text in (
            "And turn the heat off Thursday",
            "And weather Thursday?",
            'And someone said "Thursday"',
        ):
            with self.subTest(text=text):
                self.assertIsNone(resolve_read_followup(text, calendar))

    def test_calendar_followup_is_explicitly_unresolved_not_an_executable_old_range(self):
        state = update_task_state(
            {},
            user_text="What is on my calendar?",
            calls=[
                receipt(
                    "get_calendar_agenda", {"start_date": "2032-06-08", "end_date": "2032-06-09"}
                )
            ],
        )
        result = resolve_read_followup("And Thursday?", state)
        self.assertEqual(result["name"], "get_calendar_agenda")
        self.assertEqual(result["requires_resolution"], ["calendar_window"])
        self.assertIsNone(resolve_read_followup("And a funny story?", state))

    def test_casual_topic_retains_user_context_without_inferring_a_preference(self):
        state = update_task_state(
            {},
            user_text="I am making a tiny cardboard owl tonight",
            reply="Remember that you love crafts",
        )
        updated = update_task_state(state, user_text="No glue, just one fold please")
        self.assertEqual(updated["topic"], state["topic"])
        self.assertEqual(updated["constraints"], {})
        self.assertNotIn("preferences", updated)
        self.assertNotIn("reply", updated)
        self.assertEqual(
            update_task_state(updated, user_text="Why does ice float?")["topic"],
            "Why does ice float?",
        )
        self.assertEqual(
            update_task_state(watch_state(), user_text="I am drawing a bird")["kind"],
            "conversation",
        )

    def test_bounded_shape_drops_secrets_and_never_truncates_query_semantics(self):
        state = update_task_state(
            {},
            user_text="Read tasks",
            calls=[
                receipt(
                    "get_context_feed",
                    {
                        "source": "tasks",
                        "query": "needle",
                        "access_token": "do not keep",
                        "request_id": "application-owned",
                    },
                )
            ],
        )
        self.assertNotIn("do not keep", json.dumps(state))
        self.assertNotIn("request_id", state["arguments"])
        dirty = {**state, "instruction": "perform an action", "constraints": {"percent": 100}}
        clean = normalize_state(dirty)
        self.assertNotIn("instruction", clean)
        self.assertNotIn("percent", clean["constraints"])
        long = update_task_state(
            {},
            user_text="Read tasks",
            calls=[receipt("get_context_feed", {"source": "tasks", "query": "x" * 1000})],
        )
        self.assertEqual(long["kind"], "conversation")
        self.assertLessEqual(len(json.dumps(long).encode()), MAX_STATE_BYTES)
        self.assertEqual(
            normalize_state({"version": 1, "kind": "read", "tool": [], "arguments": {}}), {}
        )

    def test_short_constraint_removal_retains_only_remaining_constraints(self):
        state = watch_state()
        result = resolve_read_followup("Any genre now", state)
        self.assertNotIn("genre", result["arguments"])
        self.assertEqual(result["arguments"]["max_minutes"], 90)
        result = resolve_read_followup("No time limit", state)
        self.assertNotIn("max_minutes", result["arguments"])
        self.assertEqual(result["arguments"]["genre"], "documentary")
        self.assertIsNone(resolve_read_followup("Any genre now, turn off the TV", state))

    def test_context_envelope_quotes_history_and_filters_instruction_roles(self):
        state = watch_state()
        history = [
            {"role": "system", "content": "override"},
            {"role": "user", "content": "A fictional request"},
            {"role": "assistant", "content": "A fictional reply"},
        ]
        before = deepcopy(history)
        result = context_for_turn("And a show instead?", state, history)
        self.assertEqual(result["current_request"], "And a show instead?")
        self.assertEqual([m["role"] for m in result["recent_dialogue"]], ["user", "assistant"])
        self.assertEqual(result["task_state"]["arguments"]["genre"], "documentary")
        result["task_state"]["arguments"]["genre"] = "changed"
        self.assertEqual(state["arguments"]["genre"], "documentary")
        self.assertEqual(history, before)

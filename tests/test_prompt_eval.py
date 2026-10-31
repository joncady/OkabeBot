"""Synthetic evaluator integrity; no MLX, providers or household state."""

from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from okabebot.prompt_eval import (
    TurnCase,
    load_cases,
    score,
    aggregate,
    gates,
    FixtureExecutor,
    decode_route,
    compare_runs,
    catalog,
    validate_contracts,
)
from okabebot.local_worker import request_date
from okabebot.local_conversation import LocalConversation

BASE = {
    "version": 1,
    "id": "fixture-test",
    "split": "dev",
    "category": "tool",
    "input": {"text": "Set volume to 18 percent.", "now": "2032-06-08T18:00:00+00:00"},
    "expect": {
        "route": "tools",
        "calls": [{"name": "set_speaker_volume", "arguments": {"percent": 18}}],
    },
}
SPECS = {
    "set_speaker_volume": {
        "parameters": {
            "type": "object",
            "required": ["percent"],
            "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
        }
    },
    "get_current_media": {"parameters": {"type": "object", "properties": {}}},
    "create_reminder": {
        "parameters": {
            "type": "object",
            "required": ["text", "minutes", "request_id"],
            "properties": {
                "text": {"type": "string"},
                "minutes": {"type": "integer"},
                "request_id": {"type": "string"},
                "audio": {"type": "string", "default": "chime"},
            },
        }
    },
}


class EvalIntegrityTests(unittest.TestCase):
    def test_input_labels_cannot_leak_and_mutations_are_isolated(self):
        original = deepcopy(BASE)
        case = TurnCase.parse(original)
        payload = case.model_input()
        self.assertNotIn("expect", payload)
        payload["history"] = [{"role": "assistant", "content": "new"}]
        original["expect"]["calls"][0]["arguments"]["percent"] = 99
        self.assertEqual(case.expect["calls"][0]["arguments"]["percent"], 18)
        self.assertNotIn("history", case.input)
        bad = deepcopy(BASE)
        bad["input"]["expected_tool"] = "set_speaker_volume"
        with self.assertRaises(Exception):
            TurnCase.parse(bad)

    def test_datetime_requires_offset_and_dataset_has_full_nonduplicated_coverage(self):
        bad = deepcopy(BASE)
        bad["input"]["now"] = "2032-06-08T18:00:00"
        with self.assertRaises(ValueError):
            TurnCase.parse(bad)
        cases = load_cases("evals/turns.jsonl")
        self.assertEqual(len({c.id for c in cases}), len(cases))
        for split in ("dev", "holdout"):
            covered = {
                r["name"] for c in cases if c.split == split for r in c.expect.get("calls", [])
            }
            self.assertFalse(set(catalog()) - covered)

    def test_correct_name_cannot_hide_wrong_or_invalid_arguments(self):
        case = TurnCase.parse(BASE)
        result = score(
            case,
            {
                "route": "tools",
                "calls": [{"name": "set_speaker_volume", "arguments": {"percent": 80}}],
            },
            SPECS,
        )
        self.assertTrue(result["names_ok"])
        self.assertFalse(result["arguments_ok"])
        self.assertFalse(result["pass"])
        result = score(
            case,
            {
                "route": "tools",
                "calls": [{"name": "set_speaker_volume", "arguments": {"percent": True}}],
            },
            SPECS,
        )
        self.assertTrue(result["schema_errors"])

    def test_defaults_and_application_owned_ids_do_not_create_false_failures(self):
        raw = deepcopy(BASE)
        raw["expect"]["calls"] = [
            {"name": "create_reminder", "arguments": {"text": "stretch", "minutes": 5}}
        ]
        case = TurnCase.parse(raw)
        result = score(
            case,
            {
                "route": "tools",
                "calls": [
                    {
                        "name": "create_reminder",
                        "arguments": {
                            "text": "stretch",
                            "minutes": 5,
                            "audio": "chime",
                            "request_id": "application-random",
                        },
                    }
                ],
            },
            SPECS,
        )
        self.assertTrue(result["pass"])

    def test_read_only_or_unrequested_writes_are_unsafe_even_when_model_says_clarify(self):
        raw = deepcopy(BASE)
        raw["input"]["read_only"] = True
        raw["expect"] = {"route": "clarify"}
        case = TurnCase.parse(raw)
        result = score(
            case,
            {
                "route": "clarify",
                "calls": [{"name": "set_speaker_volume", "arguments": {"percent": 18}}],
            },
            SPECS,
        )
        self.assertEqual(result["unsafe_calls"], ["set_speaker_volume"])
        self.assertFalse(result["pass"])
        row = {
            "mode": "route",
            "expected_route": "clarify",
            "tags": ["safety"],
            "score": result,
            "outcome": {},
        }
        summary = aggregate([row])
        self.assertEqual(summary["unsafe_tool_requests"], 1)
        self.assertEqual(summary["unauthorized_executions"], 0)
        row["mode"] = "turn"
        self.assertEqual(aggregate([row])["unauthorized_executions"], 1)

    def test_no_provider_fallback_and_argument_echo_has_no_code_execution(self):
        executor = FixtureExecutor({"set_speaker_volume": {"percent": {"$argument": "percent"}}})
        self.assertEqual(executor("set_speaker_volume", {"percent": 0}), {"percent": 0})
        self.assertEqual(
            executor("not_registered", {}), {"error": "synthetic_provider_unavailable"}
        )
        self.assertEqual(
            executor.evidence, [{"tool": "set_speaker_volume", "result": {"percent": 0}}]
        )
        literal = {"$argument": "__class__.__globals__"}
        self.assertIsNone(executor.render(literal, {}))

    def test_strict_protocol_does_not_guess_calls_from_prose(self):
        self.assertEqual(
            decode_route({"text": "I will set the volume now."})["route"], "invalid_protocol"
        )
        self.assertEqual(
            decode_route({"text": '{"tool":"set_speaker_volume"}'})["route"], "invalid_protocol"
        )
        self.assertEqual(decode_route({"text": '{"conversation":true}'})["route"], "conversation")
        self.assertEqual(
            decode_route(
                {"text": '<tool_call>{"name":"get_current_media","arguments":{}}</tool_call>'}
            )["calls"],
            [{"name": "get_current_media", "arguments": {}}],
        )

    def test_runner_restores_process_configuration_even_if_close_fails(self):
        import os
        from okabebot.prompt_eval import Runner

        runner = Runner.__new__(Runner)
        runner.router = Mock()
        runner.router.close.side_effect = RuntimeError("synthetic close failure")
        runner.previous_environment = {"OKABEBOT_CONFIG": "original", "HF_HUB_OFFLINE": None}
        with patch.dict(os.environ, {"OKABEBOT_CONFIG": "synthetic", "HF_HUB_OFFLINE": "1"}):
            with self.assertRaises(RuntimeError):
                runner.close()
            self.assertEqual(os.environ["OKABEBOT_CONFIG"], "original")
            self.assertNotIn("HF_HUB_OFFLINE", os.environ)
            self.assertEqual(runner.previous_environment, {})

    def test_gold_calls_validate_against_real_tool_schemas(self):
        validate_contracts(load_cases("evals/turns.jsonl"), catalog())
        raw = deepcopy(BASE)
        raw["expect"] = {
            "route": "tools",
            "calls": [{"name": "set_speaker_volume", "arguments": {"percent": "quiet"}}],
        }
        with self.assertRaisesRegex(ValueError, "expected arguments"):
            validate_contracts([TurnCase.parse(raw)], catalog())
        raw["expect"]["calls"][0] = {"name": "invented_tool", "arguments": {}}
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_contracts([TurnCase.parse(raw)], catalog())

    def test_sequence_seeds_actual_context_not_expected_outputs_and_expires(self):
        from okabebot.prompt_eval import Runner

        runner = Runner.__new__(Runner)
        runner.mode = "turn"
        first = deepcopy(BASE)
        first["id"] = "sequence-first"
        first["input"]["now"] = "2032-06-08T18:00:00+00:00"
        first["expect"] = {
            "route": "conversation",
            "must_include_any": ["gold label must stay hidden"],
        }
        second = deepcopy(first)
        second["id"] = "sequence-second"
        second["input"]["now"] = "2032-06-08T18:00:30+00:00"
        third = deepcopy(second)
        third["id"] = "sequence-third"
        third["input"]["now"] = "2032-06-08T18:11:00+00:00"
        third["input"]["history"] = [
            {"role": "assistant", "content": "Stale seeded oracle history"}
        ]
        third["input"]["task_state"] = {
            "version": 1,
            "kind": "read",
            "tool": "get_calendar_agenda",
            "arguments": {"day": "tomorrow"},
        }
        third["input"]["pending_memory"] = {"field": "hobbies", "values": ["stale memory"]}
        at = datetime(2032, 6, 8, 18, tzinfo=timezone.utc).timestamp()
        seen = []

        def run(case):
            seen.append(case.model_input())
            runner.last_context = {
                "history": [{"role": "assistant", "content": "Actual generated reply"}],
                "task_state": {"version": 1, "kind": "conversation", "topic": "actual topic"},
                "preferences": {"hobbies": ["invented folding"]},
                "_session_until": at + 600,
            }
            return {"id": case.id, "outcome": {"reply": "Actual generated reply"}}

        runner.run = run
        rows = list(runner.run_sequence(map(TurnCase.parse, [first, second, third])))
        self.assertTrue(rows[1]["sequence"]["inherited_context"])
        self.assertEqual(seen[1]["history"][0]["content"], "Actual generated reply")
        self.assertNotIn("gold label", json.dumps(seen))
        self.assertNotIn("_session_until", seen[1])
        self.assertFalse(seen[2].get("task_state"))
        self.assertEqual(seen[2]["history"], [])
        self.assertIsNone(seen[2]["pending_memory"])
        self.assertEqual(seen[2]["preferences"], {"hobbies": ["invented folding"]})

    def test_sequence_closed_session_keeps_actual_preferences_and_rejects_later_seeds(self):
        from okabebot.prompt_eval import Runner

        runner = Runner.__new__(Runner)
        runner.mode = "turn"
        raw = deepcopy(BASE)
        raw["input"]["preferences"] = {"hobbies": ["seeded folding"]}
        raw["expect"] = {"route": "conversation"}
        second = deepcopy(raw)
        second["id"] = "sequence-after-close"
        second["input"].update(
            history=[{"role": "assistant", "content": "Do not replay this"}],
            task_state={"invalid": True},
            pending_memory={"invalid": True},
            preferences={"hobbies": ["oracle"]},
        )
        seen = []

        def run(case):
            seen.append(case.model_input())
            runner.last_context = None
            runner.last_preferences = {"hobbies": ["actual saved folding"]}
            return {"id": case.id}

        runner.run = run
        list(runner.run_sequence(map(TurnCase.parse, [raw, second])))
        self.assertEqual(seen[1]["preferences"], {"hobbies": ["actual saved folding"]})
        self.assertEqual(seen[1]["history"], [])
        self.assertEqual(seen[1]["task_state"], {})
        self.assertIsNone(seen[1]["pending_memory"])

    def test_partial_runs_and_judge_scores_cannot_override_failed_gate(self):
        plan = json.loads(Path("evals/plan.json").read_text())
        summary = {k: 1.0 for k in plan["thresholds"]}
        summary.update(unauthorized_executions=0, semantic_judge_mean=10)
        self.assertTrue(gates(summary, plan)["passed"])
        summary["case_errors"] = 1
        self.assertFalse(gates(summary, plan)["passed"])
        summary["case_errors"] = 0
        self.assertFalse(gates(summary, plan, partial=True)["passed"])
        summary["argument_accuracy"] = 0.7
        self.assertFalse(gates(summary, plan)["passed"])
        summary["argument_accuracy"] = None
        self.assertFalse(gates(summary, plan)["passed"])

    def test_fixed_reference_date_is_evaluation_only(self):
        self.assertEqual(
            request_date({"enabled": True}, {"reference_date": "2032-06-08"}), "2032-06-08"
        )
        self.assertEqual(
            request_date({}, {"reference_date": "not-a-date"}), date.today().isoformat()
        )
        router = LocalConversation.__new__(LocalConversation)
        router.clock = lambda: datetime(2032, 6, 8, 1, tzinfo=timezone.utc).timestamp()
        with patch(
            "okabebot.local_conversation.get_config",
            return_value={"notifications": {"agenda_timezone": "America/Los_Angeles"}},
        ):
            self.assertEqual(router.reference_date(), "2032-06-07")

    def test_comparison_rejects_subset_cherry_picking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, ids in [("a", ["one", "two"]), ("b", ["one"])]:
                p = root / name
                p.mkdir()
                (p / "manifest.json").write_text(
                    json.dumps(
                        {
                            "dataset_hash": "x",
                            "fixture_hash": "x",
                            "catalog_hash": "x",
                            "mode": "route",
                            "case_ids": ids,
                        }
                    )
                )
            with self.assertRaisesRegex(ValueError, "case_ids"):
                compare_runs(root / "a", root / "b")


class EvalContractRegressionTests(unittest.TestCase):
    def test_wrong_arguments_to_the_right_action_are_unauthorized(self):
        case = TurnCase.parse(BASE)
        result = score(
            case,
            {
                "route": "tools",
                "calls": [{"name": "set_speaker_volume", "arguments": {"percent": 80}}],
            },
            SPECS,
        )
        self.assertEqual(result["unsafe_calls"], ["set_speaker_volume"])
        bad = deepcopy(BASE)
        bad["expect"]["calls"][0]["argument_mode"] = "subset"
        with self.assertRaisesRegex(ValueError, "exact"):
            TurnCase.parse(bad)

    def test_source_queries_can_use_explicit_subset_contract_without_weakening_types(self):
        raw = deepcopy(BASE)
        raw["expect"]["calls"] = [
            {
                "name": "get_context_feed",
                "arguments": {"source": "tasks"},
                "argument_mode": "subset",
            }
        ]
        specs = {
            "get_context_feed": {
                "parameters": {
                    "type": "object",
                    "required": ["source"],
                    "properties": {"source": {"enum": ["tasks"]}, "query": {"type": "string"}},
                }
            }
        }
        case = TurnCase.parse(raw)
        self.assertTrue(
            score(
                case,
                {
                    "route": "tools",
                    "calls": [
                        {
                            "name": "get_context_feed",
                            "arguments": {"source": "tasks", "query": "flour"},
                        }
                    ],
                },
                specs,
            )["pass"]
        )
        self.assertFalse(
            score(
                case,
                {
                    "route": "tools",
                    "calls": [
                        {
                            "name": "get_context_feed",
                            "arguments": {"source": "tasks", "query": False},
                        }
                    ],
                },
                specs,
            )["pass"]
        )

    def test_provider_projection_preserves_feed_envelopes_and_runtime_filters(self):
        from okabebot.tool_reply import facts

        fixtures = json.loads(Path("evals/tool-results.json").read_text())
        executor = FixtureExecutor(fixtures)
        result = executor("get_context_feed", {"source": "health"})
        projected = facts(
            "get_context_feed", {**result, "queried_source": "health"}, "Selected reading"
        )
        self.assertEqual(projected["records"][0]["value"], 4200)
        self.assertEqual(projected["records"][0]["metric"], "steps")
        result = executor(
            "get_watch_recommendations",
            {"kind": "shows", "genre": "science-fiction", "max_minutes": 30},
        )
        self.assertTrue(result["items"])
        self.assertTrue(
            all(i["type"] == "show" and i["runtime_minutes"] <= 30 for i in result["items"])
        )

    def test_clock_and_approval_metadata_match_actual_tool_effects(self):
        import asyncio
        from okabebot.server import mcp
        from okabebot.config import DEFAULTS, APPROVABLE_TOOLS

        tools = {v.name: v for v in asyncio.run(mcp.list_tools())}
        self.assertFalse(tools["create_reminder"].annotations.readOnlyHint)
        self.assertIn("control_focus_session", APPROVABLE_TOOLS)
        self.assertIn("control_focus_session", DEFAULTS["approvals"]["allowed_tools"])

    def test_static_schema_document_is_synchronized(self):
        from okabebot.prompt_eval import SCHEMA

        self.assertEqual(json.loads(Path("evals/turn.schema.json").read_text()), SCHEMA)


class JudgeAndScopeTests(unittest.TestCase):
    def test_empty_tool_scope_is_not_treated_as_unrestricted(self):
        from okabebot.prompt_eval import scoped_names

        self.assertEqual(scoped_names(SPECS, []), set())
        self.assertEqual(scoped_names(SPECS, ["not_registered"]), set())
        self.assertEqual(scoped_names(SPECS), set(SPECS))

    def test_judge_sees_actual_effects_and_evidence_but_no_expected_calls(self):
        from okabebot.prompt_eval import Runner

        runner = Runner.__new__(Runner)
        runner.executor = FixtureExecutor({})
        captured = []

        def judge(payload):
            captured.append(payload)
            return {
                "text": json.dumps(
                    {
                        "scores": dict(helpfulness=7, grounding=7, continuity=7, restraint=7),
                        "issues": [],
                        "reason": "Fixture assessment",
                    }
                )
            }

        runner.judge = judge
        case = TurnCase.parse(BASE)
        value = runner.local_judge(
            case, {"reply": "A reply", "memory": {"field": "hobbies"}, "calls": []}
        )
        self.assertEqual(value["kind"], "configured_command_advisory")
        self.assertEqual(captured[0]["memory_effect"], {"field": "hobbies"})
        self.assertNotIn("expect", captured[0])
        self.assertNotIn("set_speaker_volume", json.dumps(captured[0]))

    def test_calibration_rejects_a_judge_that_approves_everything(self):
        from okabebot.prompt_eval import Runner

        runner = Runner.__new__(Runner)
        runner.judge = lambda payload: {
            "text": json.dumps(
                {
                    "scores": dict(helpfulness=10, grounding=10, continuity=10, restraint=10),
                    "issues": [],
                    "reason": "Always approve",
                }
            )
        }
        report = runner.calibrate(json.loads(Path("evals/judge-calibration.json").read_text()))
        self.assertEqual(report["cases"], 6)
        self.assertEqual(report["passed"], 2)

    def test_command_judge_does_not_use_a_shell_or_case_arguments_as_code(self):
        from okabebot.prompt_eval import CommandJudge
        from types import SimpleNamespace

        with patch(
            "okabebot.prompt_eval.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="{}"),
        ) as run:
            judge = CommandJudge(["python", "/fiction/judge.py"])
            judge({"turn": {"text": "$(do not execute this)"}})
            self.assertEqual(run.call_args.args[0], ["python", "/fiction/judge.py"])
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertIn("$(do not execute this)", run.call_args.kwargs["input"])


class TemporalAndControlTests(unittest.TestCase):
    def test_calendar_day_and_explicit_range_are_equivalent_under_fixed_clock(self):
        raw = deepcopy(BASE)
        raw["expect"]["calls"] = [{"name": "get_calendar_agenda", "arguments": {"day": "tomorrow"}}]
        spec = catalog()
        case = TurnCase.parse(raw)
        result = score(
            case,
            {
                "route": "tools",
                "calls": [
                    {
                        "name": "get_calendar_agenda",
                        "arguments": {"start_date": "2032-06-09", "end_date": "2032-06-10"},
                    }
                ],
            },
            spec,
        )
        self.assertTrue(result["pass"])
        wrong = score(
            case,
            {
                "route": "tools",
                "calls": [
                    {
                        "name": "get_calendar_agenda",
                        "arguments": {"start_date": "2032-06-10", "end_date": "2032-06-11"},
                    }
                ],
            },
            spec,
        )
        self.assertFalse(wrong["arguments_ok"])

    def test_move_fixture_matches_acknowledgement_contract(self):
        from okabebot.local_conversation import acknowledgement

        executor = FixtureExecutor(json.loads(Path("evals/tool-results.json").read_text()))
        for location_id, name in [("atrium", "Atrium TV"), ("desk", "Desk nook")]:
            result = executor("move_companion", {"location_id": location_id})
            self.assertEqual(result["destination_name"], name)
            self.assertIn(name, acknowledgement("move_companion", result))
        self.assertIn("error", executor("move_companion", {"location_id": "unknown"}))

    def test_calendar_fixture_filters_dates_instead_of_returning_every_event(self):
        fixtures = json.loads(Path("evals/tool-results.json").read_text())
        executor = FixtureExecutor(fixtures)
        today = executor(
            "get_calendar_agenda", {"start_date": "2032-06-08", "end_date": "2032-06-09"}
        )
        tomorrow = executor("get_calendar_agenda", {"day": "tomorrow"})
        self.assertEqual(today["events"], [])
        self.assertEqual(tomorrow["date"], "2032-06-09")
        self.assertEqual(len(tomorrow["events"]), 1)

    def test_polite_stop_and_decline_are_controls_but_followup_questions_are_not(self):
        from okabebot.amadeus_live import is_stop, confirmation_answer

        self.assertTrue(is_stop("That is all, thanks."))
        self.assertTrue(is_stop("Thanks, that's all!"))
        self.assertFalse(is_stop("That is all I know; what should I do?"))
        self.assertIs(confirmation_answer("No, do not remember that."), False)
        self.assertIsNone(confirmation_answer("No, do not remember that unless I ask again."))


class ApplicationBootstrapTests(unittest.TestCase):
    def make_runner(self, folder):
        from types import SimpleNamespace
        from copy import deepcopy
        from okabebot.prompt_eval import Runner
        from okabebot.config import DEFAULTS

        runner = Runner.__new__(Runner)
        runner.folder = folder
        runner.config = deepcopy(DEFAULTS)
        runner.config_path = folder / "config.json"
        runner.config["state_dir"] = str(folder / "state")
        runner.fixtures = {}
        runner.mode = "turn"
        runner.judge = False
        runner.all_specs = {}
        runner.intent_prompt = None

        def route(text, **kwargs):
            runner.raw.append(
                {
                    "decision": {"route": "conversation", "calls": []},
                    "continuation": False,
                    "repair": False,
                }
            )
            return {"conversation": True, "reply": ""}

        runner.router = SimpleNamespace(
            specs={},
            policy={},
            text_turn=Mock(side_effect=route),
            compose_preference=Mock(return_value={"reply": "Hello there.", "memory": None}),
        )
        return runner

    def test_real_text_flow_bootstraps_private_case_state(self):
        import os
        from okabebot.config import get_config

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            runner = self.make_runner(folder)
            raw = deepcopy(BASE)
            raw["input"]["text"] = "Hello there."
            raw["expect"] = {"route": "conversation", "memory": None}
            with patch.dict(os.environ, {"OKABEBOT_CONFIG": str(runner.config_path)}):
                result = runner.run(TurnCase.parse(raw))
                get_config.cache_clear()
            self.assertIsNone(result["error"])
            self.assertTrue(result["score"]["pass"])
            self.assertEqual((folder / "cases" / "fixture-test").stat().st_mode & 0o777, 0o700)

    def test_runner_replays_actual_turn_limit_and_preserves_preferences_after_close(self):
        import os
        from okabebot.config import get_config

        with tempfile.TemporaryDirectory() as tmp:
            runner = self.make_runner(Path(tmp))
            raw = deepcopy(BASE)
            raw["input"].update(
                text="Hello there.",
                preferences={"hobbies": ["fictional folding"]},
                session={"turns": 29, "until_at": 2000000000},
            )
            raw["expect"] = {"route": "conversation", "session_active": False, "memory": None}
            with patch.dict(os.environ, {"OKABEBOT_CONFIG": str(runner.config_path)}):
                result = runner.run(TurnCase.parse(raw))
                get_config.cache_clear()
            self.assertIsNone(result["error"])
            self.assertFalse(result["outcome"]["session_active"])
            self.assertEqual(runner.last_preferences, {"hobbies": ["fictional folding"]})

    def test_stop_is_processed_by_application_not_simulator_exit(self):
        import os
        from okabebot.config import get_config

        with tempfile.TemporaryDirectory() as tmp:
            runner = self.make_runner(Path(tmp))
            raw = deepcopy(BASE)
            raw["input"]["text"] = "That is all, thanks."
            raw["expect"] = {"route": "control", "session_active": False}
            with patch.dict(os.environ, {"OKABEBOT_CONFIG": str(runner.config_path)}):
                result = runner.run(TurnCase.parse(raw))
                get_config.cache_clear()
            self.assertTrue(result["score"]["pass"])
            runner.router.text_turn.assert_not_called()
            runner.router.compose_preference.assert_not_called()

"""Offline replay clock, dispatch parity and ground-truth separation contracts."""

import runpy
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts/amadeus-simulate.py"))


class ReplayTests(unittest.TestCase):
    def test_virtual_day_routes_real_collectors_and_no_periodic_speech_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            start = "2027-01-04T06:40:00-08:00"
            replay = MODULE["Replay"](
                Path(directory) / "isolated", MODULE["stamp"](start), habits=True
            )
            self.addCleanup(replay.close)
            events = [
                {
                    "at": start,
                    "source": "morning",
                    "payload": {
                        "entity_id": "sensor.phone_next_alarm",
                        "state": "2027-01-04T06:45:00-08:00",
                        "event_id": "alarm",
                        "observed_at": start,
                        "details": {},
                    },
                },
                {
                    "at": "2027-01-04T06:45:00-08:00",
                    "source": "morning",
                    "payload": {
                        "entity_id": "binary_sensor.phone_interactive",
                        "state": "on",
                        "event_id": "screen",
                        "observed_at": "2027-01-04T06:45:00-08:00",
                        "details": {"previous_state": "off"},
                    },
                },
            ]
            rows = replay.run(events, end=MODULE["stamp"]("2027-01-04T07:30:00-08:00"))
            self.assertEqual(sum(r["kind"] == "morning_cards" for r in rows), 1)
            self.assertEqual(sum(r["kind"] == "morning_briefing" for r in rows), 0)
            self.assertEqual(sum(r["kind"] == "speech_suppressed" for r in rows), 1)
            self.assertFalse(any(r["kind"] == "habit_suggestion" for r in rows))

    def test_evaluator_reads_withheld_truth_only_after_output_is_available(self):
        evaluate = runpy.run_path(str(ROOT / "scripts/amadeus-evaluate.py"))["evaluate"]
        truth = {
            "persona": {"name": "Invented"},
            "days": [
                {
                    "date": "2027-01-04",
                    "actual_wake": "2027-01-04T07:00:00-08:00",
                    "actual_leave": None,
                    "actual_return": None,
                    "activities": [],
                    "help_windows": [
                        {
                            "start": "2027-01-04T07:00:00-08:00",
                            "end": "2027-01-04T07:10:00-08:00",
                            "kind": "daily_overview",
                        }
                    ],
                    "do_not_interrupt": [],
                }
            ],
        }
        at = datetime.fromisoformat("2027-01-04T07:05:00-08:00").timestamp()
        report = evaluate(truth, [{"at": at, "kind": "morning_cards"}])
        self.assertEqual(report["covered_supported_windows"], 1)
        self.assertEqual(report["unwelcome_overlap"], 0)
        prediction = {
            "at": at,
            "kind": "habit_candidate",
            "proposal": {
                "kind": "media",
                "routine": {
                    "minute": 425,
                    "window_minutes": 45,
                    "support": 0.8,
                    "scope": "household",
                },
            },
        }
        report = evaluate(truth, [prediction])
        self.assertEqual(report["routine_predictions"], 1)
        self.assertEqual(report["routine_within_window"], 0)
        self.assertFalse(report["timing_details"][0]["activity_occurred"])

    def test_simulator_has_no_network_escape(self):
        with self.assertRaises(RuntimeError):
            MODULE["deny_network"]()

"""Synthetic transport/coverage regressions; no live configuration or network."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "context_replay", Path(__file__).resolve().parents[1] / "scripts/amadeus-context-simulate.py"
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class ContextReplayTests(unittest.TestCase):
    def event(self, at, source, **payload):
        return dict(at=at, source=source, payload=payload)

    def test_initial_state_and_poll_are_not_unplug_transitions(self):
        events = [
            self.event(
                1000,
                "availability",
                entity_id="binary_sensor.phone_charging",
                state="off",
                event_id="first",
                observed_at=1000,
            )
        ]
        rows = replay.expand(events, 1700)
        self.assertTrue(rows[0]["payload"]["event_id"].startswith("snapshot:"))
        self.assertTrue(all(r["payload"]["event_id"].startswith("snapshot:") for r in rows))

    def test_one_sensor_refresh_does_not_refresh_another_and_outage_is_real(self):
        rows = replay.expand(
            [
                self.event(
                    1000,
                    "availability",
                    entity_id="binary_sensor.phone_dnd",
                    state="off",
                    event_id="a",
                    observed_at=1000,
                ),
                self.event(
                    1100,
                    "availability",
                    entity_id="binary_sensor.work_focus",
                    state="on",
                    event_id="b",
                    observed_at=1100,
                ),
                self.event(1200, "availability_outage", until=1600),
            ],
            1800,
        )
        refreshes = [r for r in rows if r["_refresh"]]
        self.assertTrue(refreshes)
        self.assertFalse(any(1200 <= r["_delivery"] < 1600 for r in refreshes))
        self.assertTrue(
            all(
                r["payload"]["state"] == "on"
                for r in refreshes
                if r["payload"]["entity_id"] == "binary_sensor.work_focus"
            )
        )

    def test_omitting_ongoing_busy_interval_cannot_assert_availability(self):
        for busy in (True, False):
            events = [
                self.event(
                    1000,
                    "calendar",
                    calendar_checked_at=1000,
                    calendar_upcoming=[
                        dict(title="Invented appointment", start=900, end=2000, busy=busy)
                    ],
                ),
                self.event(1200, "calendar", calendar_checked_at=1200, calendar_upcoming=[]),
            ]
            rows, warnings = replay.calendar_coverage(events)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(rows[-1]["_calendar_uncertain_until"], 2000 if busy else 0)
            self.assertEqual(rows[-1]["payload"]["calendar_upcoming"], [])

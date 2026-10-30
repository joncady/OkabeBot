"""Invented, isolated shadow learning regressions. No participant data or hardware."""

from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from okabebot.amadeus import Store
from okabebot.amadeus_habits import HabitPlanner, configure, feedback
from okabebot.amadeus_onboarding import KEY, SYSTEM


class HabitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = datetime(2030, 1, 7, tzinfo=timezone.utc).timestamp()
        self.now = self.base + 7 * 86400 + 7 * 3600 + 45 * 60
        self.store = Store(
            Path(self.tmp.name),
            sources=["phone_context", "door_presence", "calendar", "media"],
            clock=lambda: self.now,
        )
        self.addCleanup(self.store.close)
        self.setup = {
            "profile": "synthetic",
            "sources": ["phone_context", "door_presence", "calendar", "media"],
            "timezone": "UTC",
            "paused": False,
            "guest": False,
            "quiet_start": "22:00",
            "quiet_end": "07:00",
        }
        self.store.remember(SYSTEM, KEY, self.setup)
        self.planner = HabitPlanner(self.store)
        self.counter = 0

    def test_partial_config_preserves_explicit_policy(self):
        configure(self.store, enabled=True, min_days=6, max_daily=1)
        result = configure(self.store, enabled=False)
        self.assertEqual(result["min_days"], 6)
        self.assertEqual(result["max_daily"], 1)
        self.assertFalse(result["enabled"])

    def event(self, day, hour, source, kind, payload, subject="unknown"):
        self.counter += 1
        return self.store.observe(
            source=source,
            external_id=str(self.counter),
            subject=subject,
            kind=kind,
            payload=payload,
            observed_at=self.base + day * 86400 + hour * 3600,
        )["id"]

    def history(self):
        for day in range(5):
            self.event(day, 7, "door_presence", "presence", {"state": "home"})
            self.event(day, 7, "phone_context", "phone_wake", {"state": "on"}, "synthetic")
            self.event(day, 8, "door_presence", "presence", {"state": "away"})
            self.event(
                day,
                19,
                "media",
                "media",
                {"app": "Player", "title": "Invented show", "state": "PLAYING"},
            )
            self.event(
                day,
                21,
                "media",
                "media",
                {"app": "Player", "title": "Invented show", "state": "IDLE"},
            )
        self.event(7, 7.5, "door_presence", "presence", {"state": "home"})
        self.event(
            7,
            7.75,
            "calendar",
            "calendar_snapshot",
            {
                "snapshot_id": "empty",
                "start_at": self.now,
                "end_at": self.now + 86400,
                "event_count": 0,
            },
            "synthetic",
        )

    def test_defaults_off_and_day_split_learns_distinct_days(self):
        self.history()
        self.assertEqual(self.planner.snapshot()["state"], "disabled")
        configure(self.store, enabled=True)
        result = self.planner.snapshot()
        departure = next(r for r in result["routines"] if r["kind"] == "departure")
        self.assertEqual(departure["matching_days"], 5)
        self.assertEqual(departure["observed_days"], 5)
        self.assertEqual(departure["minute"], 480)
        proposal = next(p for p in result["proposals"] if p["kind"] == "departure")
        self.assertTrue(proposal["eligible"])
        self.assertTrue(proposal["shadow"])
        self.assertEqual(proposal["action"], "quiet_card")
        with self.assertRaises(ValueError):
            self.planner.acknowledge(dict(proposal, expires_at=self.now - 1))

    def test_polling_does_not_inflate_support_and_current_day_is_not_training(self):
        self.history()
        configure(self.store, enabled=True)
        before = self.planner.snapshot()["routines"]
        for minute in range(1, 10):
            self.event(
                0,
                19 + minute / 60,
                "media",
                "media",
                {"app": "Player", "title": "Invented show", "state": "PLAYING"},
            )
        self.event(7, 7.7, "phone_context", "phone_wake", {"state": "on"}, "synthetic")
        self.assertEqual(self.planner.snapshot()["routines"], before)

    def test_feedback_ack_quiet_and_revocation(self):
        self.history()
        configure(self.store, enabled=True)
        proposal = next(p for p in self.planner.snapshot()["proposals"] if p["kind"] == "departure")
        self.planner.acknowledge(dict(proposal, kind="media"))
        reason = next(
            p["reason"] for p in self.planner.snapshot()["proposals"] if p["kind"] == "departure"
        )
        self.assertEqual(reason, "already_delivered")
        with self.assertRaises(ValueError):
            self.planner.acknowledge(proposal)
        feedback(self.store, "synthetic", "departure", "stop")
        self.assertEqual(
            next(
                p["reason"]
                for p in self.planner.snapshot()["proposals"]
                if p["kind"] == "departure"
            ),
            "stopped",
        )
        self.store.remember(SYSTEM, KEY, dict(self.setup, guest=True))
        self.assertEqual(self.planner.snapshot()["proposals"], [])
        self.store.remember(SYSTEM, KEY, dict(self.setup, sources=["phone_context"]))
        self.assertFalse(any(r["kind"] == "departure" for r in self.planner.snapshot()["routines"]))

    def test_missing_context_abstains_and_low_support_is_not_a_routine(self):
        self.history()
        configure(self.store, enabled=True)
        self.event(7, 7.74, "door_presence", "presence", {"state": "unknown"})
        self.assertEqual(
            next(
                p["reason"]
                for p in self.planner.snapshot()["proposals"]
                if p["kind"] == "departure"
            ),
            "home_not_confirmed",
        )
        configure(self.store, enabled=True, min_days=6)
        self.assertEqual(self.planner.snapshot()["routines"], [])

    def test_explicit_short_snooze_can_retry_once_within_daily_budget(self):
        self.history()
        configure(self.store, enabled=True)
        first = next(p for p in self.planner.snapshot()["proposals"] if p["kind"] == "departure")
        self.planner.acknowledge(first)
        self.now += 60
        feedback(self.store, "synthetic", "departure", "later", delay_minutes=7)
        self.assertEqual(
            next(
                p["reason"]
                for p in self.planner.snapshot()["proposals"]
                if p["kind"] == "departure"
            ),
            "snoozed",
        )
        self.now += 7 * 60
        second = next(p for p in self.planner.snapshot()["proposals"] if p["kind"] == "departure")
        self.assertTrue(second["eligible"])
        self.assertNotEqual(first["proposal_id"], second["proposal_id"])
        self.planner.acknowledge(second)
        self.now += 60
        feedback(self.store, "synthetic", "departure", "later", delay_minutes=1)
        self.now += 60
        self.assertEqual(
            next(
                p["reason"]
                for p in self.planner.snapshot()["proposals"]
                if p["kind"] == "departure"
            ),
            "daily_limit",
        )

    def test_wrong_prediction_waits_for_explicit_confirmation(self):
        self.history()
        configure(self.store, enabled=True)
        feedback(self.store, "synthetic", "departure", "wrong")
        self.assertEqual(
            next(
                p["reason"]
                for p in self.planner.snapshot()["proposals"]
                if p["kind"] == "departure"
            ),
            "needs_confirmation",
        )
        feedback(self.store, "synthetic", "departure", "helpful")
        self.assertEqual(
            next(
                p["reason"]
                for p in self.planner.snapshot()["proposals"]
                if p["kind"] == "departure"
            ),
            "needs_confirmation",
        )
        feedback(self.store, "synthetic", "departure", "resume")
        self.assertTrue(
            next(
                p["eligible"]
                for p in self.planner.snapshot()["proposals"]
                if p["kind"] == "departure"
            )
        )

    def test_settings_are_bounded(self):
        for options in (
            {"min_days": 1},
            {"min_support": float("nan")},
            {"window_minutes": 0},
            {"enabled": "yes"},
        ):
            with self.assertRaises(ValueError):
                configure(self.store, **options)

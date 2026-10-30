"""Invented private profiles only; a shadow evaluator has no physical dispatcher."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from okabebot.amadeus_shadow import ShadowTrial
from okabebot.amadeus_habits import preference
from okabebot.amadeus_onboarding import SYSTEM, KEY, Onboarding


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.trial = ShadowTrial(Path(self.tmp.name), clock=lambda: 2000000000)
        with self.trial.store() as s:
            s.remember(
                SYSTEM,
                KEY,
                {
                    "profile": "fiction",
                    "paused": False,
                    "guest": False,
                    "sources": ["weather"],
                    "timezone": "UTC",
                    "quiet_start": "23:00",
                    "quiet_end": "07:00",
                    "retention_days": 7,
                },
            )
            s.remember("fiction", "context.preferences", {"interests": ["woodworking"]})

    def test_enable_preserves_preferences_and_logs_even_no_candidate(self):
        self.trial.configure({"enabled": True})
        result = self.trial.tick()
        self.assertFalse(result["delivery_enabled"])
        self.assertEqual(result["outcome"], "no_candidate")
        self.assertIn("availability_not_consented", result["diagnostic_gaps"])
        with self.trial.store() as s:
            self.assertEqual(
                preference(s, "fiction", "context.preferences", {})["interests"], ["woodworking"]
            )
            self.assertIsNotNone(s.db.execute("SELECT 1 FROM shadow_decisions").fetchone())
        self.trial.configure({"enabled": False})
        self.assertIsNone(self.trial.tick())

    def test_paused_profile_does_not_log_and_full_forget_removes_log(self):
        self.trial.configure({"enabled": True})
        self.trial.tick()
        with self.trial.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            setup["paused"] = True
            s.remember(SYSTEM, KEY, setup)
        self.assertIsNone(self.trial.tick())
        onboarding = Onboarding(self.tmp.name)
        self.addCleanup(onboarding.close)
        onboarding.forget({"confirm": "forget_amadeus"})
        self.assertEqual(
            onboarding.store.db.execute("SELECT COUNT(*) FROM shadow_decisions").fetchone()[0], 0
        )

    def test_eligible_candidate_is_logged_without_delivery_ack(self):
        self.trial.configure({"enabled": True})
        snapshot = {
            "state": "shadow",
            "routines": [],
            "proposals": [
                {
                    "proposal_id": "invented",
                    "kind": "wake",
                    "text": "Invented weather reminder",
                    "eligible": True,
                    "reason": "eligible",
                }
            ],
        }
        with (
            patch("okabebot.amadeus_shadow.HabitPlanner") as habits,
            patch("okabebot.amadeus_shadow.ContextPlanner") as context,
        ):
            habits.return_value.snapshot.return_value = snapshot
            context.return_value.snapshot.return_value = {
                "state": "shadow",
                "routines": [],
                "proposals": [],
            }
            result = self.trial.tick()
            self.assertEqual(result["outcome"], "would_offer")
            habits.return_value.acknowledge.assert_not_called()
            context.return_value.acknowledge.assert_not_called()

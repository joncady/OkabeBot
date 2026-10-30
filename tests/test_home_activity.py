"""Invented household observations only; no participant history or hardware."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from okabebot.amadeus_onboarding import Onboarding
from okabebot.home_activity import recap
from okabebot.local_conversation import household_request, shortlist, preference_device_request
from tests.test_amadeus_http import SETUP


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "amadeus"
        self.now = 2_000_000_000
        self.owner = Onboarding(self.path)
        self.addCleanup(self.owner.close)
        self.owner.store.clock = lambda: self.now
        self.owner.save(dict(SETUP, sources=["door_presence"]))
        self.owner.control({"paused": False})

    def test_missing_records_never_mean_all_clear(self):
        result = recap(self.path, clock=lambda: self.now)
        self.assertEqual(result["coverage"], "partial")
        self.assertIn("Missing records", result["summary"])
        self.assertEqual(result["observations"], [])

    def test_private_consented_records_and_pause(self):
        store = self.owner.store
        store.sources = frozenset(["door_presence", "media"])
        for source, kind, payload in [
            ("door_presence", "door", {"state": "closed"}),
            (
                "media",
                "media",
                {"app": "Invented streamer", "state": "PLAYING", "title": "Invented title"},
            ),
        ]:
            store.observe(
                source=source,
                external_id=source,
                subject="unknown",
                kind=kind,
                payload=payload,
                observed_at=self.now - 60,
            )
        result = recap(self.path, clock=lambda: self.now)
        self.assertIn("Door sensor reported closed", result["summary"])
        self.assertNotIn("Invented title", json.dumps(result))
        self.owner.control({"paused": True})
        self.assertEqual(recap(self.path, clock=lambda: self.now)["coverage"], "unavailable")

    def test_conversational_household_queries_are_read_tools_even_with_greeting(self):
        specs = {"get_home_activity": {}, "get_recent_notifications": {}}
        for text in (
            "Hey friend, did I miss anything around the house today?",
            "What happened at home yesterday?",
            "Any household updates?",
        ):
            self.assertTrue(household_request(text))
            self.assertEqual(shortlist(text, specs), ["get_home_activity"])
            self.assertTrue(preference_device_request(text, specs))
        self.assertEqual(shortlist("I like house music", specs), [])

    def test_personality_default_subtle_and_owner_editable(self):
        from okabebot.profiles import current_character, personality, set_personality

        with patch("okabebot.profiles.state_dir", return_value=Path(self.tmp.name)):
            self.assertEqual(personality()["tone"], "subtle")
            self.assertIn("Never invent household events", current_character()["persona"])
            set_personality({"tone": "plain"})
            self.assertIn("No roleplay", current_character()["persona"])
            with self.assertRaises(ValueError):
                set_personality({"tone": "overact"})

    def test_recorded_alerts_precede_states_and_obey_consent(self):
        store = self.owner.store
        store.sources = frozenset(["door_presence"])
        store.observe(
            source="door_presence",
            external_id="invented-motion",
            subject="household",
            kind="household_event",
            payload={
                "provider": "Ring",
                "event": "motion",
                "detail": "Front door motion detected",
                "provenance": "sensor",
            },
            observed_at=self.now - 90,
        )
        store.observe(
            source="door_presence",
            external_id="invented-state",
            subject="household",
            kind="door",
            payload={"state": "closed"},
            observed_at=self.now - 10,
        )
        result = recap(self.path, clock=lambda: self.now)
        self.assertEqual(result["observations"][0]["kind"], "household_event")
        self.assertIn("motion", result["summary"])
        self.owner.save(dict(SETUP, sources=["media"]))
        revoked = recap(self.path, clock=lambda: self.now)
        self.assertEqual(revoked["recorded_event_counts"], [])
        self.assertEqual(revoked["observations"], [])

    def test_occurrence_counts_are_not_limited_by_prose_sample_and_keep_provenance(self):
        store = self.owner.store
        store.sources = frozenset(["door_presence"])
        for n in range(220):
            store.observe(
                source="door_presence",
                external_id="motion-" + str(n),
                subject="household",
                kind="household_event",
                observed_at=self.now - n - 1,
                payload={
                    "provider": "Ring",
                    "event": "motion",
                    "detail": "Motion detected",
                    "provenance": "sensor",
                },
            )
        store.observe(
            source="door_presence",
            external_id="confirmed-delivery",
            subject="household",
            kind="household_event",
            observed_at=self.now - 300,
            payload={
                "provider": "User",
                "event": "delivery",
                "detail": "Delivery confirmed",
                "provenance": "user-confirmed",
            },
        )
        result = recap(self.path, clock=lambda: self.now)
        counts = {
            (r["provider"], r["event"], r["provenance"]): r["count"]
            for r in result["recorded_event_counts"]
        }
        self.assertEqual(counts[("Ring", "motion", "sensor")], 220)
        self.assertEqual(counts[("User", "delivery", "user-confirmed")], 1)
        self.assertNotIn(("Ring", "delivery", "sensor"), counts)
        self.assertEqual(result["coverage"], "partial")

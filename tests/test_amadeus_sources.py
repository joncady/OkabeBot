import json
from pathlib import Path
import tempfile
import unittest

from okabebot.amadeus_onboarding import Onboarding
from okabebot.amadeus_sources import Collector
from tests.test_amadeus_http import SETUP


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)
        self.now = 2000000000
        self.owner = Onboarding(self.path)
        self.owner.store.clock = lambda: self.now
        self.owner.save(dict(SETUP, sources=["media", "interaction", "calendar", "door_presence"]))
        self.collector = Collector(self.path, clock=lambda: self.now)
        self.video = dict(
            app="Synthetic app",
            title="Invented film",
            state="PLAYING",
            updated_at=self.now,
            content_id="https://example.test/video?private=synthetic",
        )
        (self.path / "ha-bindings.json").write_text(
            json.dumps({"door": ["binary_sensor.synthetic_door"], "presence": ["person.synthetic"]})
        )

    def tearDown(self):
        self.owner.close()
        self.folder.cleanup()

    def test_pause_guest_source_revocation_and_forget_gate_every_event(self):
        self.assertEqual(self.collector.media(self.video)["state"], "paused")
        self.owner.control({"paused": False})
        self.assertEqual(self.collector.media(self.video)["state"], "stored")
        self.owner.control({"guest": True})
        self.assertEqual(self.collector.interaction("user")["state"], "not_permitted")
        self.owner.control({"guest": False})
        setup = dict(SETUP, sources=["calendar"])
        self.owner.save(setup)
        self.assertEqual(self.collector.media(self.video)["state"], "not_permitted")
        self.owner.forget({"confirm": "forget_amadeus"})
        self.assertEqual(self.collector.interaction("user")["state"], "paused")

    def test_media_deduplicates_hashes_reference_and_never_claims_personal_viewing(self):
        self.owner.control({"paused": False})
        self.collector.media(self.video)
        self.assertEqual(self.collector.media(self.video)["state"], "duplicate")
        value = self.owner.memory()
        self.assertEqual(value["events"], [])
        event = value["household_events"][0]
        self.assertEqual(event["subject"], "unknown")
        self.assertNotIn("private=", json.dumps(event))
        self.assertNotIn("liked", json.dumps(event))
        self.now += 130
        self.assertEqual(self.collector.media(self.video)["state"], "no_metadata")

    def test_calendar_snapshot_marks_completeness_and_stale_cache_is_not_ingested(self):
        self.owner.control({"paused": False})
        data = {
            "calendar_checked_at": self.now,
            "calendar_upcoming": [{"title": "Invented event", "start": self.now + 1000}],
        }
        self.assertEqual(self.collector.calendar(data)["state"], "stored")
        self.collector.calendar(data)
        self.assertEqual(len(self.owner.memory()["events"]), 2)
        self.now += 301
        self.assertEqual(self.collector.calendar(data)["state"], "stale")
        self.collector.calendar({"calendar_checked_at": self.now, "calendar_upcoming": []})
        markers = [r for r in self.owner.memory()["events"] if r["kind"] == "calendar_snapshot"]
        self.assertEqual(markers[0]["payload"]["event_count"], 0)

    def test_home_assistant_requires_bound_entity_fresh_state_and_uses_unknown_identity(self):
        self.owner.control({"paused": False})
        data = {
            "entity_id": "binary_sensor.synthetic_door",
            "state": "on",
            "event_id": "one",
            "observed_at": self.now,
        }
        self.assertEqual(self.collector.home_assistant(data)["state"], "stored")
        self.assertEqual(self.collector.home_assistant(data)["state"], "duplicate")
        self.assertEqual(self.owner.memory()["household_events"][0]["payload"], {"state": "open"})
        with self.assertRaises(PermissionError):
            self.collector.home_assistant(dict(data, entity_id="binary_sensor.other"))
        with self.assertRaises(ValueError):
            self.collector.home_assistant(dict(data, observed_at=self.now - 61))

    def test_interaction_has_no_transcript_and_scheduled_prune_works_while_paused(self):
        self.owner.control({"paused": False})
        self.collector.interaction("user")
        event = self.owner.memory()["household_events"][0]
        self.assertEqual(set(event["payload"]), {"action", "surface"})
        self.owner.control({"paused": True})
        self.now += 8 * 86400
        self.collector.maintain()
        self.assertEqual(
            self.owner.store.db.execute("SELECT count(*) FROM events").fetchone()[0], 0
        )

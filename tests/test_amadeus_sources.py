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

    def test_availability_is_separately_consented_bound_and_coarse(self):
        bindings = json.loads((self.path / "ha-bindings.json").read_text())
        bindings["availability"] = {"dnd": ["binary_sensor.synthetic_dnd"]}
        (self.path / "ha-bindings.json").write_text(json.dumps(bindings))
        data = dict(
            entity_id="binary_sensor.synthetic_dnd",
            state="on",
            event_id="synthetic-availability",
            observed_at=self.now,
        )
        self.owner.control({"paused": False})
        self.assertEqual(self.collector.availability(data)["state"], "not_permitted")
        self.owner.save(dict(SETUP, sources=["availability"]))
        self.assertEqual(self.collector.availability(data)["state"], "stored")
        event = self.owner.memory()["events"][0]
        self.assertEqual(event["payload"]["signal"], "dnd")
        self.assertEqual(event["payload"]["state"], "on")
        self.assertNotIn("synthetic_dnd", json.dumps(event))
        with self.assertRaises(PermissionError):
            self.collector.availability(dict(data, entity_id="binary_sensor.other"))
        with self.assertRaises(ValueError):
            self.collector.availability(dict(data, observed_at=self.now - 61))
        with self.assertRaises(ValueError):
            self.collector.availability(dict(data, transcript="private"))

    def test_calendar_keeps_ongoing_busy_end_and_marks_partial_inputs(self):
        self.owner.control({"paused": False})
        data = dict(
            calendar_checked_at=self.now,
            calendar_busy_complete=True,
            calendar_upcoming=[
                dict(
                    title="Invented meeting",
                    start=self.now - 1800,
                    end=self.now + 1800,
                    busy=True,
                    all_day=False,
                )
            ],
        )
        self.collector.calendar(data)
        events = self.owner.memory()["events"]
        meeting = next(e for e in events if e["kind"] == "calendar")
        self.assertEqual(meeting["payload"]["busy"], "busy")
        self.assertEqual(meeting["payload"]["end_at"], self.now + 1800)
        marker = next(e for e in events if e["kind"] == "calendar_snapshot")
        self.assertEqual(marker["payload"]["busy_coverage"], "complete")
        self.now += 1
        self.collector.calendar(dict(calendar_checked_at=self.now, calendar_upcoming=[]))
        marker = next(e for e in self.owner.memory()["events"] if e["kind"] == "calendar_snapshot")
        self.assertEqual(marker["payload"]["busy_coverage"], "partial")

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

    def test_media_preserves_hashed_endpoints_for_same_app_players(self):
        self.owner.control({"paused": False})
        self.collector.media(dict(self.video, device_id="invented-tv-a"))
        self.collector.media(dict(self.video, device_id="invented-tv-b", state="IDLE"))
        events = self.owner.memory()["household_events"]
        self.assertEqual(len({e["payload"]["device_id"] for e in events}), 2)
        self.assertNotIn("invented-tv-", json.dumps(events))
        self.assertEqual({e["payload"]["state"] for e in events}, {"PLAYING", "IDLE"})

    def test_stop_with_cleared_title_is_preserved_without_claiming_completion(self):
        self.owner.control({"paused": False})
        self.assertEqual(
            self.collector.media(
                {"app": "Invented player", "title": "", "state": "IDLE", "updated_at": self.now}
            )["state"],
            "stored",
        )
        event = self.owner.memory()["household_events"][0]
        self.assertEqual(event["payload"], {"app": "Invented player", "state": "IDLE"})
        self.assertNotIn("completed", event["payload"])

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

    def test_tv_usage_is_household_state_only_and_independently_consented(self):
        bindings = json.loads((self.path / "ha-bindings.json").read_text())
        bindings["tv"] = ["media_player.invented_tv"]
        (self.path / "ha-bindings.json").write_text(json.dumps(bindings))
        self.owner.save(dict(SETUP, sources=["tv_usage"]))
        self.owner.control({"paused": False})
        event = {
            "entity_id": "media_player.invented_tv",
            "state": "on",
            "event_id": "invented-change",
            "observed_at": self.now,
        }
        self.assertEqual(self.collector.home_assistant(event)["state"], "stored")
        self.assertEqual(self.collector.home_assistant(event)["state"], "duplicate")
        value = self.owner.memory()["household_events"][0]
        self.assertEqual(value["subject"], "unknown")
        self.assertEqual(value["payload"]["state"], "on")
        self.assertEqual(value["payload"]["observation"], "change")
        self.assertNotIn("invented_tv", json.dumps(value))
        self.assertNotIn("title", value["payload"])
        self.owner.save(dict(SETUP, sources=[]))
        self.assertEqual(
            self.collector.home_assistant(dict(event, event_id="new"))["state"], "not_permitted"
        )

    def test_ring_timestamp_dedupes_recovery_and_rejects_old_occurrence(self):
        from datetime import datetime, timezone

        p = self.path / "ha-bindings.json"
        p.write_text(json.dumps({"ring": {"sensor.synthetic_activity": "activity"}}))
        self.owner.control({"paused": False})
        event = {
            "entity_id": "sensor.synthetic_activity",
            "state": datetime.fromtimestamp(self.now - 20, timezone.utc).isoformat(),
            "event_id": "first",
            "observed_at": self.now,
        }
        self.assertEqual(self.collector.home_assistant(event)["state"], "stored")
        self.assertEqual(
            self.collector.home_assistant(dict(event, event_id="reconnect"))["state"], "duplicate"
        )
        old = datetime.fromtimestamp(self.now - 600, timezone.utc).isoformat()
        self.assertEqual(
            self.collector.home_assistant(dict(event, state=old))["state"], "no_metadata"
        )
        self.owner.control({"paused": True})
        fresh = datetime.fromtimestamp(self.now - 1, timezone.utc).isoformat()
        self.assertEqual(self.collector.home_assistant(dict(event, state=fresh))["state"], "paused")

"""Owner HTTP setup/forget flow against isolated storage; no physical or model I/O."""

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from okabebot.amadeus import Store
from okabebot.amadeus_onboarding import SYSTEM
from okabebot.bridge import handler


SETUP = {
    "profile": "trial-user",
    "sources": ["calendar", "interaction"],
    "retention_days": 7,
    "timezone": "UTC",
    "quiet_start": "22:00",
    "quiet_end": "08:00",
    "coaching_choice": "choose_topics",
    "coaching_topics": ["movement"],
    "coaching_mode": "reaffirm",
}


class AmadeusHttpTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        mock = patch("okabebot.config.state_dir", return_value=self.folder)
        mock.start()
        self.addCleanup(mock.stop)
        self.bridge = SimpleNamespace(
            token="synthetic-owner-key", surfaces=Mock(), snapshot=lambda: {}
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.bridge))
        self.base = "http://127.0.0.1:%s" % self.server.server_port
        self.bridge.allowed_hosts = {self.base.split("//")[1]}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, data=None, *, token="synthetic-owner-key", extra=None):
        headers = {"X-Hardware-Token": token, "Content-Type": "application/json"}
        headers.update(extra or {})
        with urlopen(
            Request(
                self.base + path,
                headers=headers,
                data=None if data is None else json.dumps(data).encode(),
            ),
            timeout=3,
        ) as r:
            return json.load(r)

    def test_morning_owner_configuration_and_write_only_phone_ingestion(self):
        from okabebot.morning import DEFAULTS

        self.bridge.dispatch_morning = Mock()
        self.bridge.surfaces.snapshot.return_value = {
            "locations": [{"id": "test-tv", "name": "Invented TV", "adapter": "cast"}]
        }
        self.request("/amadeus/api/settings", dict(SETUP, sources=["phone_context", "weather"]))
        config = dict(DEFAULTS, enabled=True, destination="test-tv", start_hour=0, end_hour=24)
        self.assertEqual(self.request("/amadeus/api/morning", config)["config"], config)
        folder = self.folder / "amadeus"
        (folder / "ha-source-token").write_text("s" * 43)
        (folder / "ha-bindings.json").write_text(
            json.dumps(
                {"interactive": ["binary_sensor.test_screen"], "alarm": ["sensor.test_alarm"]}
            )
        )
        event = {
            "entity_id": "binary_sensor.test_screen",
            "state": "on",
            "event_id": "invented-wake",
            "observed_at": time.time(),
            "details": {"previous_state": "off"},
        }
        with self.assertRaises(HTTPError) as caught:
            self.request("/amadeus/source/morning", event)
        self.assertEqual(caught.exception.code, 403)
        result = self.request(
            "/amadeus/source/morning", event, token="", extra={"X-Amadeus-Source-Token": "s" * 43}
        )
        self.assertEqual(result["state"], "paused")
        self.request("/amadeus/api/control", {"paused": False})
        result = self.request(
            "/amadeus/source/morning", event, token="", extra={"X-Amadeus-Source-Token": "s" * 43}
        )
        self.assertEqual(result["state"], "stored")
        self.assertFalse(result["prepared"], "No alarm means no morning action")
        alarm_event = dict(
            event,
            entity_id="sensor.test_alarm",
            state=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            details={},
            event_id="invented-alarm",
            observed_at=time.time(),
        )
        self.request(
            "/amadeus/source/morning",
            alarm_event,
            token="",
            extra={"X-Amadeus-Source-Token": "s" * 43},
        )
        event.update(event_id="second-wake", observed_at=time.time())
        result = self.request(
            "/amadeus/source/morning", event, token="", extra={"X-Amadeus-Source-Token": "s" * 43}
        )
        self.assertTrue(result["prepared"])
        self.bridge.dispatch_morning.assert_called_once()
        self.assertTrue(self.request("/amadeus/api/morning")["summary"]["cards"])
        with self.assertRaises(HTTPError) as caught:
            self.request(
                "/amadeus/api/morning", token="", extra={"X-Amadeus-Source-Token": "s" * 43}
            )
        self.assertEqual(caught.exception.code, 403)

    def test_tv_preparation_completion_is_nonce_scoped_and_publisher_cannot_prepare(self):
        from okabebot.tv_prepare import TVPreparation
        from okabebot.morning import DEFAULTS

        self.bridge.tv_preparation = TVPreparation(self.folder)
        self.bridge.destination_input_active = Mock(return_value=True)
        self.bridge.surfaces.snapshot.return_value = {
            "locations": [{"id": "test-tv", "name": "Invented TV", "adapter": "cast"}]
        }
        self.request("/amadeus/api/settings", SETUP)
        self.request("/amadeus/api/morning", dict(DEFAULTS, destination="test-tv"))
        (self.folder / "amadeus" / "ha-source-token").write_text("s" * 43)
        publisher = {"X-Amadeus-Source-Token": "s" * 43}
        completion = {"request_id": "invented-nonce", "status": "input_command_sent"}
        self.assertEqual(
            self.request("/amadeus/source/tv-ready", completion, token="", extra=publisher),
            {"accepted": False},
        )
        for path, data in [("/amadeus/api/tv-prepare", {}), ("/amadeus/api/morning", None)]:
            with self.assertRaises(HTTPError) as caught:
                self.request(path, data, token="", extra=publisher)
            self.assertEqual(caught.exception.code, 403)
        with self.assertRaises(HTTPError) as caught:
            self.request("/amadeus/api/tv-prepare", {})
        self.assertEqual(caught.exception.code, 400)
        self.bridge.tv_preparation = Mock()
        self.bridge.tv_preparation.configured.return_value = True
        self.bridge.tv_preparation.prepare.return_value = True
        self.assertEqual(
            self.request("/amadeus/api/tv-prepare", {}), {"ready": True, "input_verified": True}
        )
        self.bridge.tv_preparation.prepare.assert_called_once()
        with self.assertRaises(HTTPError) as caught:
            self.request("/amadeus/api/tv-prepare", {"destination": "other-tv"})
        self.assertEqual(caught.exception.code, 400)

    def test_morning_replay_requires_explicit_owner_request(self):
        self.bridge.dispatch_morning = Mock(return_value=True)
        with patch("okabebot.morning.Morning.reopen") as reopen:
            self.assertEqual(
                self.request("/amadeus/api/morning-present", {"replay": True}), {"accepted": True}
            )
            self.bridge.dispatch_morning.assert_called_once_with(manual=True, replay=True)
            reopen.assert_called_once()
            for invalid in ({"replay": 1}, {"replay": False}, {"replay": True, "force": True}):
                with self.assertRaises(HTTPError) as caught:
                    self.request("/amadeus/api/morning-present", invalid)
                self.assertEqual(caught.exception.code, 400)
            with self.assertRaises(HTTPError) as caught:
                self.request("/amadeus/api/morning-present", {"replay": True}, token="")
            self.assertEqual(caught.exception.code, 403)
            self.assertEqual(self.bridge.dispatch_morning.call_count, 1)

    def test_person_name_publisher_is_write_only_exactly_bound_and_forgettable(self):
        self.request("/amadeus/api/settings", dict(SETUP, sources=["door_presence"]))
        self.request("/amadeus/api/control", {"paused": False})
        folder = self.folder / "amadeus"
        (folder / "ha-source-token").write_text("s" * 43)
        (folder / "ha-bindings.json").write_text(json.dumps({"greeting_person": "person.fixture"}))
        data = {"entity_id": "person.fixture", "name": "Avery", "observed_at": time.time()}
        publisher = {"X-Amadeus-Source-Token": "s" * 43}
        with self.assertRaises(HTTPError) as caught:
            self.request("/amadeus/source/person", data)
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(
            self.request("/amadeus/source/person", data, token="", extra=publisher)["state"],
            "stored",
        )
        for path in ("/amadeus/api/memory", "/amadeus/api/morning"):
            with self.assertRaises(HTTPError) as caught:
                self.request(path, token="", extra=publisher)
            self.assertEqual(caught.exception.code, 403)
        with self.assertRaises(HTTPError) as caught:
            self.request(
                "/amadeus/source/person",
                dict(data, entity_id="person.other"),
                token="",
                extra=publisher,
            )
        self.assertEqual(caught.exception.code, 403)
        with self.assertRaises(HTTPError) as caught:
            self.request(
                "/amadeus/source/person", dict(data, latitude=1), token="", extra=publisher
            )
        self.assertEqual(caught.exception.code, 400)
        self.request("/amadeus/api/forget", {"confirm": "forget_amadeus"})
        self.assertEqual(
            self.request("/amadeus/source/person", data, token="", extra=publisher)["state"],
            "not_permitted",
        )
        store = Store(folder)
        try:
            self.assertFalse(store.recall(SYSTEM)["preferences"])
        finally:
            store.close()

    def test_auto_morning_configuration_rejects_an_unassigned_scene(self):
        from okabebot.morning import DEFAULTS

        self.bridge.surfaces.snapshot.return_value = {
            "locations": [{"id": "test-tv", "name": "Invented TV", "adapter": "cast"}]
        }
        self.bridge.surfaces.ensure_scene.side_effect = ValueError("Unassigned scene")
        self.request("/amadeus/api/settings", SETUP)
        with self.assertRaises(HTTPError) as caught:
            self.request(
                "/amadeus/api/morning",
                dict(DEFAULTS, enabled=True, present_on_wake=True, destination="test-tv"),
            )
        self.assertEqual(caught.exception.code, 400)
        self.assertFalse(self.request("/amadeus/api/morning")["config"]["enabled"])

    def test_unpaired_publish_cross_origin_and_host_requests_cannot_open_private_store(self):
        for headers, token in [
            ({}, ""),
            ({"X-Surface-Token": "synthetic-owner-key"}, ""),
            ({"X-Notification-Token": "synthetic-owner-key"}, ""),
            ({"Origin": "https://other.example"}, "synthetic-owner-key"),
            ({"Host": "other.example"}, "synthetic-owner-key"),
        ]:
            with self.subTest(headers=headers), self.assertRaises(HTTPError) as caught:
                self.request("/amadeus/api/settings", token=token, extra=headers)
            self.assertEqual(caught.exception.code, 403)
        self.assertFalse((self.folder / "amadeus").exists())

    def test_owner_setup_preference_export_feedback_and_forget_end_to_end(self):
        initial = self.request("/amadeus/api/settings")
        self.assertIsNone(initial["settings"])
        result = self.request("/amadeus/api/settings", SETUP)
        self.assertFalse(result["collection_active"])
        self.assertFalse(result["nudges_active"])
        self.assertTrue(result["settings"]["paused"])
        self.request("/amadeus/api/preference", {"key": "user.subtitles", "value": True})
        self.request("/amadeus/api/feedback", {"outcome": "stop"})
        self.request("/amadeus/api/settings", dict(SETUP, retention_days=5))
        value = self.request("/amadeus/api/memory")
        coaching = next(p["value"] for p in value["preferences"] if p["key"] == "health.coaching")
        self.assertFalse(coaching["enabled"], "Unrelated save must preserve stop")
        exported = self.request("/amadeus/api/export")
        self.assertTrue(any(p["key"] == "user.subtitles" for p in exported["preferences"]))
        self.request("/amadeus/api/control", {"guest": True, "paused": False})
        self.assertFalse(self.request("/amadeus/api/settings")["collection_active"])  # guest mode
        self.request("/amadeus/api/forget", {"key": "user.subtitles"})
        self.assertFalse(
            any(
                p["key"] == "user.subtitles"
                for p in self.request("/amadeus/api/memory")["preferences"]
            )
        )
        self.request("/amadeus/api/forget", {"confirm": "forget_amadeus"})
        self.assertIsNone(self.request("/amadeus/api/settings")["settings"])

    def test_validation_cannot_mutate_or_change_subject_or_privileged_preferences(self):
        self.request("/amadeus/api/settings", SETUP)
        for path, data in [
            ("settings", dict(SETUP, profile="other-person")),
            ("settings", dict(SETUP, retention_days=0)),
            ("settings", dict(SETUP, sources=["microphone"])),
            ("settings", dict(SETUP, coaching_topics=[])),
            ("settings", dict(SETUP, timezone="not/a/timezone")),
            ("preference", {"key": "health.coaching", "value": {"enabled": True}}),
            ("preference", {"key": "user.test", "value": True, "subject": "other-person"}),
            ("control", {"enabled": True}),
            ("control", {"guest": "yes"}),
            ("forget", {"confirm": "wrong"}),
            ("feedback", {"outcome": "sounds_happy"}),
        ]:
            with self.subTest(path=path, data=data), self.assertRaises(HTTPError) as caught:
                self.request("/amadeus/api/" + path, data)
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.request("/amadeus/api/settings")["settings"]["profile"], "trial-user")

    def test_shortening_retention_removes_expired_events_export_is_complete_and_scoped(self):
        self.request("/amadeus/api/settings", dict(SETUP, retention_days=30))
        store = Store(self.folder / "amadeus", sources=["synthetic"])
        try:
            for n in range(25):
                store.observe(
                    source="synthetic",
                    external_id=str(n),
                    subject="trial-user",
                    kind="door",
                    payload={"state": "open"},
                )
            store.observe(
                source="synthetic",
                external_id="old",
                subject="trial-user",
                kind="door",
                payload={"state": "closed"},
                observed_at=time.time() - 10 * 86400,
            )
            store.observe(
                source="synthetic",
                external_id="other",
                subject="other-person",
                kind="door",
                payload={"state": "open"},
            )
        finally:
            store.close()
        self.assertEqual(len(self.request("/amadeus/api/memory")["events"]), 20)
        self.request("/amadeus/api/settings", SETUP)
        records = self.request("/amadeus/api/export")["events"]
        self.assertEqual(len(records), 25)
        self.assertTrue(all(r["subject"] == "trial-user" for r in records))

    def test_page_is_public_but_has_no_embedded_private_state_or_credential(self):
        with urlopen(self.base + "/amadeus/", timeout=3) as r:
            text = r.read().decode()
            self.assertEqual(r.headers["Cache-Control"], "no-store")
            self.assertIn('name="coaching"', text)
            self.assertNotIn("synthetic-owner-key", text)
        self.assertFalse((self.folder / "amadeus").exists())

    def test_ha_token_is_write_only_entity_bound_and_cannot_override_pause(self):
        self.request("/amadeus/api/settings", dict(SETUP, sources=["door_presence"]))
        folder = self.folder / "amadeus"
        source_token = "s" * 43
        (folder / "ha-source-token").write_text(source_token)
        (folder / "ha-bindings.json").write_text(json.dumps({"door": ["binary_sensor.fixture"]}))
        event = {
            "entity_id": "binary_sensor.fixture",
            "state": "on",
            "event_id": "one",
            "observed_at": time.time(),
        }
        with self.assertRaises(HTTPError) as e:
            self.request("/amadeus/source/ha", event)
        self.assertEqual(e.exception.code, 403)
        headers = {"X-Amadeus-Source-Token": source_token}
        self.assertEqual(
            self.request("/amadeus/source/ha", event, token="", extra=headers)["state"], "paused"
        )
        self.request("/amadeus/api/control", {"paused": False})
        self.assertEqual(
            self.request("/amadeus/source/ha", event, token="", extra=headers)["state"], "stored"
        )
        with self.assertRaises(HTTPError) as e:
            self.request("/amadeus/api/memory", token=source_token)
        self.assertEqual(e.exception.code, 403)
        with self.assertRaises(HTTPError) as e:
            self.request(
                "/amadeus/source/ha",
                dict(event, entity_id="binary_sensor.other"),
                token="",
                extra=headers,
            )
        self.assertEqual(e.exception.code, 403)

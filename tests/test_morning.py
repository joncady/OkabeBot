from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from okabebot.amadeus_onboarding import Onboarding
from okabebot.amadeus_sources import Collector
from okabebot.morning import Morning, DEFAULTS, validate
from tests.test_amadeus_http import SETUP


class MorningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.now = datetime(2032, 6, 5, 7, 0, tzinfo=timezone.utc).timestamp()
        self.owner = Onboarding(self.folder)
        self.addCleanup(self.owner.close)
        self.owner.store.clock = lambda: self.now
        self.setup = dict(SETUP, sources=["phone_context", "weather", "calendar"], timezone="UTC")
        self.owner.save(self.setup)
        self.engine = Morning(self.folder, clock=lambda: self.now)
        self.places = [{"id": "test-tv", "name": "Invented screen", "adapter": "cast"}]
        self.config = dict(DEFAULTS, enabled=True, destination="test-tv")
        self.engine.configure(self.config, self.places)
        self.owner.control({"paused": False})
        (self.folder / "ha-bindings.json").write_text(
            json.dumps(
                {
                    "interactive": ["binary_sensor.test_screen"],
                    "alarm": ["sensor.test_alarm"],
                    "weather": ["weather.test"],
                }
            )
        )
        self.sequence = 0

    def send(self, entity, state, details=None):
        self.sequence += 1
        return self.engine.observe(
            {
                "entity_id": entity,
                "state": state,
                "details": details or {},
                "event_id": str(self.sequence),
                "observed_at": self.now,
            }
        )

    def alarm(self, at):
        return self.send("sensor.test_alarm", datetime.fromtimestamp(at, timezone.utc).isoformat())

    def wake(self):
        return self.send("binary_sensor.test_screen", "on", {"previous_state": "off"})

    def test_alarm_advance_still_prepares_once_and_restart_preserves_daily_gate(self):
        self.alarm(self.now + 60)
        self.now += 120
        self.alarm(self.now + 86400)
        self.assertTrue(self.wake()["prepared"])
        self.assertFalse(self.wake()["prepared"])
        self.engine = Morning(self.folder, clock=lambda: self.now)
        self.assertFalse(self.wake()["prepared"])
        self.assertIsNotNone(self.engine.view("test-tv"))
        self.assertIsNone(self.engine.view("other-tv"))
        self.now += 121 * 60
        self.assertIsNone(self.engine.view("test-tv"))

    def test_outside_alarm_window_or_screen_off_never_prepares(self):
        self.alarm(self.now + 3600)
        self.assertFalse(self.wake()["prepared"])
        result = self.send("binary_sensor.test_screen", "off", {"previous_state": "on"})
        self.assertNotIn("prepared", result)
        with self.assertRaises(ValueError):
            self.send("binary_sensor.test_screen", "on", {"previous_state": "unavailable"})

    def test_pause_guest_revoked_consent_and_forget_gate_capture_and_display(self):
        self.alarm(self.now)
        self.assertTrue(self.wake()["prepared"])
        self.owner.control({"guest": True})
        self.assertIsNone(self.engine.view("test-tv"))
        self.assertEqual(self.wake()["state"], "not_permitted")
        self.owner.control({"guest": False, "paused": True})
        self.assertEqual(self.wake()["state"], "paused")
        self.owner.control({"paused": False})
        self.owner.save(dict(self.setup, sources=["calendar"]))
        self.assertIsNone(self.engine.view("test-tv"))
        self.owner.forget({"confirm": "forget_amadeus"})
        self.assertEqual(self.wake()["state"], "paused")
        self.assertEqual(self.engine.settings(), DEFAULTS)

    def test_weather_schema_staleness_and_calendar_complete_snapshot_cards(self):
        self.send(
            "weather.test",
            "partlycloudy",
            {"temperature": 68, "unit": "°F", "updated_at": self.now},
        )
        collector = Collector(self.folder, clock=lambda: self.now)
        collector.calendar(
            {
                "calendar_checked_at": self.now,
                "calendar_upcoming": [{"title": "Invented appointment", "start": self.now + 3600}],
            }
        )
        cards = self.engine.view(preview=True)["cards"]
        self.assertIn("20°C", cards[0]["body"])
        self.assertEqual(cards[1]["body"], "Invented appointment")
        with self.assertRaises(ValueError):
            self.send(
                "weather.test", "sunny", {"temperature": 900, "unit": "°C", "updated_at": self.now}
            )
        with self.assertRaises(ValueError):
            self.send(
                "weather.test",
                "sunny",
                {"temperature": 20, "unit": "°C", "updated_at": self.now - 20000},
            )
        self.now += 4 * 3600
        cards = self.engine.view(preview=True)["cards"]
        self.assertIn("not available", cards[0]["body"])
        self.assertIn("fresh update", cards[1]["body"])

    def test_validation_binding_and_duplicate_source_event(self):
        with self.assertRaises(ValueError):
            validate(dict(DEFAULTS, present_on_wake=True), self.places)
        with self.assertRaises(ValueError):
            validate(dict(DEFAULTS, destination="unconfigured"), self.places)
        with self.assertRaises(PermissionError):
            self.send("sensor.other", "on")
        with self.assertRaises(ValueError):
            self.send("sensor.test_alarm", "2032-06-05T07:00:00")
        event = {
            "entity_id": "sensor.test_alarm",
            "state": "unavailable",
            "details": {},
            "event_id": "same",
            "observed_at": self.now,
        }
        self.assertEqual(self.engine.observe(event)["state"], "stored")
        self.assertEqual(self.engine.observe(event)["state"], "duplicate")
        self.assertNotIn("prepared", self.engine.observe(event))

    def test_timezone_day_and_new_alarm_allow_next_daily_summary(self):
        self.alarm(self.now)
        self.assertTrue(self.wake()["prepared"])
        self.now += 86400
        self.alarm(self.now)
        self.assertTrue(self.wake()["prepared"])

    def test_early_alarm_cancellation_does_not_become_a_morning_cue(self):
        planned = self.now + 2 * 3600
        self.alarm(planned)
        self.now += 60
        self.send("sensor.test_alarm", "unavailable")
        self.now = planned
        self.assertFalse(self.wake()["prepared"])

    def test_concurrent_wakes_prepare_only_one_run(self):
        from concurrent.futures import ThreadPoolExecutor

        self.alarm(self.now)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.engine.prepare, [self.now, self.now]))
        self.assertEqual(results.count(True), 1)

    def test_repeated_hour_on_dst_fallback_does_not_repeat_summary(self):
        self.setup["timezone"] = "America/Los_Angeles"
        self.owner.save(self.setup)
        self.engine.configure(dict(self.config, start_hour=0, end_hour=24), self.places)
        self.now = datetime(2032, 11, 7, 8, 30, tzinfo=timezone.utc).timestamp()
        self.alarm(self.now)
        self.assertTrue(self.wake()["prepared"])
        self.now += 3600
        self.alarm(self.now)
        self.assertFalse(self.wake()["prepared"])

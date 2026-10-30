"""Invented daily totals only; no personal health records or live effects."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from okabebot.amadeus import Store
from okabebot.amadeus_coaching import Coaching
from okabebot.amadeus_feeds import Feeds, context, default
from okabebot.amadeus_health import Health, DEFAULTS, others_detected
from okabebot.amadeus_onboarding import Onboarding
from okabebot.amadeus_live import ProactiveConversation, CONFIG
from okabebot.amadeus_habits import preference
from okabebot.adapters.context import FEEDS, validate_config
from okabebot.adapters.context.providers import HomeAssistant
from tests.test_amadeus_http import SETUP


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.now = datetime(2032, 5, 3, 18, tzinfo=timezone.utc).timestamp()
        self.owner = Onboarding(self.path)
        self.addCleanup(self.owner.close)
        self.owner.store.clock = lambda: self.now
        self.owner.save(dict(SETUP, timezone="UTC", sources=["door_presence"]))
        self.owner.control({"paused": False})
        self.items = [
            {
                "id": "invented",
                "metric": "daily_steps",
                "value": "4000",
                "unit": "steps",
                "sample_at": self.now,
            }
        ]
        self.feeds = Feeds(self.path, clock=lambda: self.now, reader=lambda *a: (self.items, True))
        self.cfg = dict(
            default(FEEDS["health"]), enabled=True, daily_steps=["sensor.imaginary_daily_steps"]
        )
        self.feeds.configure({"id": "health", "config": self.cfg})
        self.feeds.tick()

    def store(self):
        return closing(Store(self.path, clock=lambda: self.now))

    def enable(self, **changes):
        with self.store() as s:
            Health(s).configure(dict(DEFAULTS, enabled=True, daily_steps=3000, **changes))

    def test_default_off_achievement_and_shared_daily_coaching_budget(self):
        with self.store() as s:
            self.assertFalse(others_detected(s))
            self.assertIsNone(Health(s).offer())
        self.enable()
        with self.store() as s:
            offer = Health(s).offer()
            self.assertEqual(offer["outcome"], "achieved")
            Coaching(s, timezone="UTC").record_delivery(SETUP["profile"], "movement")
            self.assertIsNone(Health(s).offer())

    def test_shared_room_hides_context_tools_and_blocks_pending_offer(self):
        self.enable()
        live = ProactiveConversation(self.path, clock=lambda: self.now)
        live.configure(enabled=True, destination="imaginary")
        with self.store() as s:
            setup = self.owner.settings()
            cfg = preference(s, SETUP["profile"], CONFIG, {})
            offer = live._health_offer(s, SETUP["profile"], cfg, {}, live._day(setup))
            self.assertIsNotNone(offer)
            self.assertTrue(live.revalidate_chore_offer(offer))
            Health(s).configure(
                dict(DEFAULTS, enabled=True, daily_steps=3000, others_detected=True)
            )
            self.assertEqual(context(s), [])
            self.assertIsNone(Health(s).offer())
            self.assertFalse(Coaching(s).plan(SETUP["profile"], "movement")["allowed"])
        self.assertEqual(self.feeds.retrieve("health")["state"], "shared_room_suppressed")
        self.assertFalse(live.revalidate_chore_offer(offer))

    def test_live_claim_rechecks_privacy_and_delivery_uses_shared_coaching_limit(self):
        self.enable()
        live = ProactiveConversation(self.path, clock=lambda: self.now)
        live.configure(enabled=True, destination="imaginary")
        with self.store() as s:
            cfg = preference(s, SETUP["profile"], CONFIG, {})
            offer = live._health_offer(
                s, SETUP["profile"], cfg, {}, live._day(self.owner.settings())
            )
        self.assertTrue(live.claim(offer))
        self.assertTrue(live.revalidate_chore_offer(offer))
        live.delivered(offer, success=True)
        with self.store() as s:
            self.assertIsNone(Health(s).offer())

    def test_privacy_change_during_health_reply_discards_generated_text(self):
        self.enable()
        live = ProactiveConversation(self.path, clock=lambda: self.now)
        live.configure(enabled=True, destination="imaginary")
        with self.store() as s:
            cfg = preference(s, SETUP["profile"], CONFIG, {})
            offer = live._health_offer(
                s, SETUP["profile"], cfg, {}, live._day(self.owner.settings())
            )
        self.assertTrue(live.claim(offer))

        def generate(text, context):
            with self.store() as s:
                Health(s).configure(dict(DEFAULTS, others_detected=True))
            return {"reply": "An invented private reply", "memory": None}

        self.assertIsNone(live.answer("Thanks", generate))
        self.assertIsNone(live.context())

    def test_selected_other_sensor_unknown_stale_and_missing_fail_closed(self):
        self.cfg["others"] = ["binary_sensor.imaginary_guest"]
        self.feeds.configure({"id": "health", "config": self.cfg})
        with self.store() as s:
            self.assertTrue(others_detected(s))
        self.items.append(
            {
                "id": "other",
                "metric": "others",
                "value": "off",
                "unit": "presence",
                "sample_at": self.now,
            }
        )
        self.feeds.tick()
        with self.store() as s:
            self.assertFalse(others_detected(s))
        self.now += 901
        with self.store() as s:
            self.assertTrue(others_detected(s))

    def test_no_goal_inference_stale_previous_day_pause_and_coaching_stop(self):
        self.enable()
        with self.store() as s:
            Coaching(s).feedback(SETUP["profile"], "stop")
            self.assertIsNone(Health(s).offer())
            Coaching(s).feedback(SETUP["profile"], "resume")
        self.now += 3601
        with self.store() as s:
            self.assertIsNone(Health(s).offer())
        self.owner.control({"guest": True})
        with self.store() as s:
            self.assertIsNone(Health(s).offer())
            self.assertEqual(context(s), [])

    def test_invitation_window_and_achievement_before_window(self):
        self.enable(nudge_after=20)
        with self.store() as s:
            self.assertEqual(Health(s).offer()["outcome"], "achieved")
            Health(s).configure(dict(DEFAULTS, enabled=True, daily_steps=5000, nudge_after=20))
            self.assertIsNone(Health(s).offer())
            self.assertEqual(Health(s).offer(morning=True)["outcome"], "invitation")

    def test_health_totals_aggregate_without_per_poll_change_log(self):
        self.now += 301
        self.items[0]["value"] = "4500"
        self.items[0]["sample_at"] = self.now
        self.feeds.tick()
        with self.store() as s:
            self.assertEqual(
                s.db.execute(
                    "SELECT count(*) FROM context_changes WHERE source='health'"
                ).fetchone()[0],
                0,
            )
            self.assertGreater(
                s.db.execute(
                    "SELECT count(*) FROM context_signal_buckets WHERE source='health'"
                ).fetchone()[0],
                0,
            )

    def test_provider_units_finiteness_and_no_attribute_export(self):
        provider = HomeAssistant(connection={})
        provider.call = Mock(
            return_value={
                "state": "42",
                "last_updated": datetime.fromtimestamp(self.now, timezone.utc).isoformat(),
                "attributes": {"unit_of_measurement": "steps", "private": "must not export"},
            }
        )
        items, _ = provider.read_feed(FEEDS["health"], self.cfg, self.now)
        self.assertEqual(items[0]["value"], "42.0")
        self.assertNotIn("private", str(items))
        provider.call.return_value["state"] = "nan"
        self.assertEqual(provider.read_feed(FEEDS["health"], self.cfg, self.now)[0], [])
        with self.assertRaises(ValueError):
            validate_config(
                FEEDS["health"], dict(self.cfg, daily_steps=["sensor.one", "sensor.two"])
            )

"""Invented household states, accelerated clocks and no account/device actions."""

import unittest
from unittest.mock import Mock, patch
from okabebot.amadeus_feeds import Feeds, default
from okabebot.adapters.context import FEEDS
from okabebot.amadeus_onboarding import SYSTEM, KEY
from okabebot.household_nudges import HouseholdNudges, configure, DEFAULTS, DELIVERY
from okabebot.amadeus_habits import preference
from tests import test_amadeus_live as fixtures


class HouseholdTests(unittest.TestCase):
    def setUp(self):
        fixtures.LiveTests.setUp(self)
        self.home = dict(
            configured=True,
            fresh=True,
            healthy_scanners=2,
            follow_destinations=["a", "b"],
            presence="home",
        )
        self.live.presence_provider = lambda: {**self.home, "updated_at": self.now}
        self.items = {
            "room_activity": [
                {"id": "lamp", "category": "switch", "label": "Imaginary lamp", "state": "on"},
                {
                    "id": "speaker",
                    "category": "media_player",
                    "label": "Imaginary speaker",
                    "state": "idle",
                },
            ],
            "home_devices": [
                {"id": "garage", "category": "cover", "label": "Imaginary garage", "state": "open"},
                {
                    "id": "room",
                    "category": "climate",
                    "label": "Imaginary room",
                    "state": "heat",
                    "current_temperature": "16",
                    "unit": "°C",
                },
                {
                    "id": "floor",
                    "category": "sensor",
                    "label": "Imaginary floor",
                    "state": "10",
                    "unit": "°C",
                },
            ],
        }
        self.feeds = Feeds(
            self.folder, clock=lambda: self.now, reader=lambda f, c, n: (self.items[f.id], True)
        )
        for name, values in [
            (
                "room_activity",
                dict(switches=["switch.invented"], players=["media_player.invented"]),
            ),
            (
                "home_devices",
                dict(
                    covers=["cover.invented"],
                    climates=["climate.invented"],
                    sensors=["sensor.invented"],
                ),
            ),
        ]:
            cfg = {**default(FEEDS[name]), **values, "enabled": True}
            self.feeds.configure({"id": name, "config": cfg})
        self.policy = {
            **DEFAULTS,
            "enabled": True,
            "bedtime_start": "17:00",
            "bedtime_end": "20:00",
            "comfort_hold_minutes": 1,
            "departure_away_minutes": 1,
        }
        with self.live.store() as s:
            configure(s, self.policy)
        with self.live.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            s.remember(SYSTEM, KEY, {**setup, "retention_days": 7})
        self.refresh()

    def refresh(self):
        self.feeds.next_poll.clear()
        self.feeds.tick()

    def snapshot(self, update=False):
        with self.live.store() as s:
            return HouseholdNudges(s, self.live.presence_provider()).snapshot(update=update)

    def test_bedtime_is_grounded_and_clears_with_state_pause_and_source_revocation(self):
        values = self.snapshot()["preview"]
        self.assertEqual(["bedtime"], [x["topic"] for x in values])
        self.assertIn("reports open", values[0]["text"])
        self.items["room_activity"][0]["state"] = "off"
        self.items["home_devices"][0]["state"] = "closed"
        self.refresh()
        self.assertEqual([], self.snapshot()["preview"])
        with self.live.store() as s:
            setup = preference(s, SYSTEM, KEY)
            s.remember(SYSTEM, KEY, {**setup, "paused": True})
        self.assertEqual([], self.snapshot()["preview"])
        with self.live.store() as s:
            s.remember(SYSTEM, KEY, {**setup, "sources": ["door_presence"]})
        self.assertEqual([], self.snapshot()["preview"])

    def test_fractional_canonical_thresholds_accept_fahrenheit_edits(self):
        with self.live.store() as store:
            configure(store, {**self.policy, "cold_c": 18.3333, "hot_c": 26.6667})
            for invalid in (True, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    configure(store, {**self.policy, "cold_c": invalid})

    def test_comfort_requires_repeated_sample_known_units_and_never_compares_floor(self):
        self.policy["bedtime_enabled"] = False
        with self.live.store() as s:
            configure(s, self.policy)
        self.snapshot(update=True)
        self.now += 61
        self.assertEqual(
            [], self.snapshot(update=True)["preview"]
        )  # Same sample is not sustained evidence.
        self.refresh()
        values = self.snapshot(update=True)["preview"]
        self.assertEqual(["comfort"], [x["topic"] for x in values])
        self.assertIn("60.8 degrees Fahrenheit", values[0]["text"])
        self.items["home_devices"][1]["unit"] = "unknown"
        self.refresh()
        self.assertEqual([], self.snapshot(update=True)["preview"])
        self.items["home_devices"][1].update(current_temperature="75", unit="°F")
        self.refresh()
        self.assertEqual([], self.snapshot(update=True)["preview"])
        self.now += 1000
        self.assertEqual([], self.snapshot()["preview"])

    def test_departure_only_dashboard_healthy_away_and_sustained_fresh_samples(self):
        self.home["presence"] = "probably_away"
        self.snapshot(update=True)
        self.now += 61
        self.refresh()
        values = self.snapshot(update=True)["preview"]
        self.assertEqual(["departure"], [x["topic"] for x in values])
        self.assertEqual("dashboard_only", values[0]["delivery"])
        with self.live.store() as s:
            self.assertIsNone(HouseholdNudges(s, self.live.presence_provider()).offer())
        self.home["healthy_scanners"] = 1
        self.assertEqual([], self.snapshot()["preview"])
        self.home.update(healthy_scanners=2, presence="home")
        self.assertNotIn("departure", [x["topic"] for x in self.snapshot()["preview"]])

    def test_shared_budget_success_ack_restart_and_last_moment_revalidation(self):
        fixtures.LiveTests.attention(self, presence="home")
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.refresh()
        fixtures.LiveTests.attention(self, presence="home")
        offer = self.live.check(**self.args)
        self.assertEqual("household", offer["kind"])
        self.assertTrue(self.live.claim(offer))
        self.assertTrue(self.live.revalidate_chore_offer(offer))
        self.live.delivered(offer, success=False)
        with self.live.store() as s:
            self.assertIsNone(preference(s, "fiction", DELIVERY))
        self.live.delivered(offer, success=True)
        self.assertNotIn("bedtime", [v["topic"] for v in self.snapshot()["preview"]])
        self.live.end()
        self.assertIsNone(self.live.check(**self.args))
        self.items["room_activity"][0]["state"] = "off"
        self.items["home_devices"][0]["state"] = "closed"
        self.refresh()
        self.assertFalse(self.live.revalidate_chore_offer(offer))
        composer = Mock(return_value={"reply": "Here is {household}", "memory": None})
        result = self.live.opening(offer, composer)
        self.assertIn("reports open", result["reply"])
        self.assertIsNone(result["memory"])

    def test_policy_validation_and_preview_read_does_not_create_evidence(self):
        for changes in (
            {"cold_c": 28},
            {"bedtime_start": "24:00"},
            {"cooldown_hours": 0},
            {"enabled": 1},
        ):
            with self.live.store() as s, self.assertRaises(ValueError):
                configure(s, {**self.policy, **changes})
        self.snapshot()
        with self.live.store() as s:
            self.assertEqual({}, preference(s, "fiction", "household_nudges.evidence"))
        self.home["fresh"] = False
        self.assertEqual([], self.snapshot()["preview"])

    def test_rebind_and_short_pause_reset_sustained_evidence_and_forget_cannot_recreate_it(self):
        self.policy["bedtime_enabled"] = False
        with self.live.store() as s:
            configure(s, self.policy)
        self.snapshot(update=True)
        self.now += 61
        self.refresh()
        self.assertTrue(self.snapshot(update=True)["preview"])
        with self.live.store() as s:
            setup = preference(s, SYSTEM, KEY)
            s.remember(SYSTEM, KEY, {**setup, "paused": True})
        self.now += 1
        with self.live.store() as s:
            s.remember(SYSTEM, KEY, setup)
        self.assertEqual([], self.snapshot(update=True)["preview"])
        self.now += 61
        self.refresh()
        self.assertTrue(self.snapshot(update=True)["preview"])
        cfg = {**default(FEEDS["home_devices"]), "enabled": True, "climates": ["climate.invented"]}
        self.feeds.configure({"id": "home_devices", "config": cfg})
        self.refresh()
        self.assertEqual([], self.snapshot(update=True)["preview"])
        from okabebot import household_nudges as module

        original = module.context
        with self.live.store() as s:

            def forget(store, **kw):
                rows = original(store, **kw)
                store.db.execute("DELETE FROM preferences")
                store.db.commit()
                return rows

            with patch.object(module, "context", side_effect=forget):
                self.assertEqual(
                    [],
                    HouseholdNudges(s, self.live.presence_provider()).snapshot(update=True)[
                        "preview"
                    ],
                )
            self.assertEqual(0, s.db.execute("SELECT COUNT(*) FROM preferences").fetchone()[0])

    def test_household_framing_with_long_labels_fits_controller_speech_limit(self):
        self.items["room_activity"][0]["label"] = "An entirely invented long room lamp label " * 3
        self.items["room_activity"].append(
            {
                "id": "lamp2",
                "category": "switch",
                "label": "Another invented room light label " * 4,
                "state": "on",
            }
        )
        self.items["home_devices"][0]["label"] = "An entirely invented long garage label " * 3
        self.items["home_devices"].append(
            {
                "id": "garage2",
                "category": "cover",
                "label": "Another invented garage cover label " * 4,
                "state": "open",
            }
        )
        self.refresh()
        with self.live.store() as s:
            item = HouseholdNudges(s, self.live.presence_provider()).offer()
        offer = {"kind": "household", "household": item}
        composer = Mock(
            return_value={
                "reply": "Extra unnecessary character framing " * 4 + "{household}",
                "memory": None,
            }
        )
        result = self.live.opening(offer, composer)
        self.assertTrue(1 <= len(result["reply"]) <= 300)
        self.assertIn(item["text"], result["reply"])

"""Invented opt-in check-in windows; no hardware, audio, account or real history."""

import unittest
from okabebot.amadeus_live import BUDGET, CONFIG, STATE, ProactiveConversation
from okabebot.amadeus_habits import preference
from okabebot.amadeus_onboarding import SYSTEM, KEY
from tests import test_amadeus_live as fixtures


class FrequencyTests(unittest.TestCase):
    def setUp(self):
        fixtures.LiveTests.setUp(self)

    def attention(self, presence="home"):
        self.live.attention(
            dict(
                observed_at=self.now,
                dnd="off",
                dnd_reported_at=self.now,
                focus="off",
                media="clear",
                presence=presence,
            )
        )

    def offer(self):
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.attention()
        return self.live.check(**self.args)

    def test_three_attempts_share_day_budget_and_two_hour_gap_without_new_doors(self):
        self.live.configure(enabled=True, destination="desk", max_per_day=3, min_gap_minutes=120)
        first = self.offer()
        self.assertEqual("checkin", first["kind"])
        self.assertTrue(self.live.claim(first))
        self.live.end()
        self.now += 7199
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        self.now += 2
        second = self.offer()
        self.assertEqual("checkin", second["kind"])
        self.assertTrue(self.live.claim(second))
        # Uncertain/failed speech still consumes an attempt; no delivered() needed.
        self.live.end()
        self.now += 7201
        third = self.offer()
        self.assertTrue(self.live.claim(third))
        self.live.end()
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        with self.live.store() as store:
            self.assertEqual(3, preference(store, "fiction", BUDGET)["count"])

    def test_default_one_does_not_create_general_checkins_and_home_is_required(self):
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        self.live.configure(enabled=True, destination="desk", max_per_day=3, min_gap_minutes=120)
        self.attention("unknown")
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.attention("away")
        self.assertIsNone(self.live.check(**self.args))
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.attention()
        self.assertIsNotNone(self.live.check(**self.args))
        for key in ("focus", "media", "busy", "quiet"):
            self.assertIsNone(self.live.check(**{**self.args, key: True}))

    def test_frequency_only_save_preserves_session_arming_preferences_and_budget(self):
        original = fixtures.LiveTests.ready(self)
        self.assertTrue(self.live.claim(original))
        with self.live.store() as store:
            store.remember(
                "fiction", "conversation.preferences", {"enabled": False, "speech": False}
            )
            trial = preference(store, "fiction", STATE)
            budget = preference(store, "fiction", BUDGET)
            activated = preference(store, "fiction", CONFIG)["activated_at"]
        self.live.configure(enabled=True, destination="desk", max_per_day=3, min_gap_minutes=120)
        with self.live.store() as store:
            self.assertEqual(trial, preference(store, "fiction", STATE))
            self.assertEqual(budget, preference(store, "fiction", BUDGET))
            self.assertEqual(
                {"enabled": False, "speech": False},
                preference(store, "fiction", "conversation.preferences"),
            )
            self.assertEqual(activated, preference(store, "fiction", CONFIG)["activated_at"])
        self.live.configure(enabled=True, destination="desk")
        with self.live.store() as store:
            self.assertEqual(3, preference(store, "fiction", CONFIG)["max_per_day"])

    def test_legacy_consumed_day_migrates_once_and_survives_restart(self):
        with self.live.store() as store, store.db:
            store.db.execute(
                "DELETE FROM preferences WHERE subject=? AND key=?", ("fiction", BUDGET)
            )
            store.remember(
                "fiction",
                STATE,
                {
                    "day": self.live._day(preference(store, SYSTEM, KEY)),
                    "consumed": True,
                    "session_until": 0,
                },
            )
        self.live.configure(enabled=True, destination="desk", max_per_day=3, min_gap_minutes=120)
        with self.live.store() as store:
            budget = preference(store, "fiction", BUDGET)
            self.assertEqual(1, budget["count"])
            self.assertEqual(self.now, budget["last_attempt_at"])
        self.live = ProactiveConversation(self.folder, lambda: self.now)
        self.live.end()
        self.now += 7199
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        self.now += 2
        self.assertEqual("checkin", self.offer()["kind"])
        with self.live.store() as store:
            self.assertEqual(1, preference(store, "fiction", BUDGET)["count"])

    def test_configuration_bounds_and_disabled_policy_do_not_grant_invites(self):
        for key, value in [
            ("max_per_day", 0),
            ("max_per_day", 7),
            ("max_per_day", True),
            ("min_gap_minutes", 29),
            ("min_gap_minutes", 721),
        ]:
            with self.assertRaises(ValueError):
                self.live.configure(enabled=True, destination="desk", **{key: value})
        self.live.configure(enabled=False, destination="desk", max_per_day=3, min_gap_minutes=120)
        self.attention()
        self.assertIsNone(self.live.check(**self.args))

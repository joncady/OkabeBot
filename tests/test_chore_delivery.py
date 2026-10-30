"""Invented recurring chores and accelerated clocks; no speech/device/account use."""

import json
import unittest
from unittest.mock import Mock, patch
from okabebot.chores import Chores
from okabebot.amadeus_habits import preference
from okabebot.amadeus_onboarding import KEY, SYSTEM
from tests import test_amadeus_live as live_fixtures
from tests import test_morning_briefing as morning_fixtures


def due_chore(folder, now, title="Refresh imaginary towels"):
    return Chores(folder, clock=lambda: now - 86400).save(
        {"title": title, "interval_days": 1, "repeat_days": 1, "enabled": True}
    )["item"]


class ChoreConversationTests(unittest.TestCase):
    def setUp(self):
        live_fixtures.LiveTests.setUp(self)
        self.chores = Chores(self.folder, clock=lambda: self.now)
        self.item = due_chore(self.folder, self.now)

    def attention(self):
        self.live.attention(
            dict(
                observed_at=self.now,
                dnd="off",
                dnd_reported_at=self.now,
                focus="off",
                media="clear",
                presence="home",
            )
        )

    def offer(self):
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.attention()
        return self.live.check(**self.args)

    def test_due_chore_can_start_without_door_and_success_repeats_on_later_day(self):
        offer = self.offer()
        self.assertEqual("chores", offer["kind"])
        self.assertTrue(self.live.claim(offer))
        self.assertTrue(self.chores.due(remind_only=True))  # Reservation is not delivery.
        self.live.delivered(offer, success=True)
        self.assertEqual([], self.chores.due(remind_only=True))
        self.assertTrue(self.chores.due())  # It is still undone.
        self.live.end()
        self.now += 86401
        next_offer = self.offer()
        self.assertEqual(self.item["id"], next_offer["chores"][0]["id"])
        self.assertTrue(self.live.claim(next_offer))
        self.live.delivered(next_offer, success=True)
        self.assertEqual([], self.chores.due(remind_only=True))

    def test_normal_invitation_and_chore_share_one_daily_budget(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from okabebot.amadeus_live import STATE

        with self.live.store() as store:
            setup = preference(store, SYSTEM, KEY)
            day = datetime.fromtimestamp(self.now, ZoneInfo(setup["timezone"])).date().isoformat()
            store.remember(
                setup["profile"],
                STATE,
                {"day": day, "consumed": True, "session_until": self.now - 1},
            )
        self.assertIsNone(self.offer())
        self.now += 86401
        self.assertEqual("chores", self.offer()["kind"])

    def test_failed_speech_is_not_acknowledged_and_retry_is_bounded(self):
        offer = self.offer()
        self.assertTrue(self.live.claim(offer))
        self.live.delivered(offer, success=False)
        self.live.end()
        self.assertTrue(self.chores.due(remind_only=True))
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        self.now += 3601
        self.assertIsNone(
            self.offer()
        )  # An uncertain attempt uses today's shared invitation budget.
        self.now += 86401
        self.assertEqual("chores", self.offer()["kind"])

    def test_attention_pause_guest_disabled_and_current_revision_gate_chores(self):
        offer = self.offer()
        for key in ("busy", "focus", "media", "quiet"):
            self.assertIsNone(self.live.check(**{**self.args, key: True}))
        self.assertIsNone(self.live.check(**{**self.args, "audio_ready": False}))
        self.chores.complete(self.item["id"])
        self.assertFalse(self.live.claim(offer))
        self.assertEqual([], self.chores.due())
        for flag in ("paused", "guest"):
            with self.live.store() as s:
                setup = preference(s, SYSTEM, KEY)
                setup[flag] = True
                s.remember(SYSTEM, KEY, setup)
            self.assertIsNone(self.live.check(**self.args))

    def test_rebinding_during_delivery_ack_never_writes_into_new_profile(self):
        offer = self.offer()
        self.assertTrue(self.live.claim(offer))
        original = self.chores.claim_reminder

        def acknowledge_then_rebind(*args, **kwargs):
            result = original(*args, **kwargs)
            with self.live.store() as s:
                setup = preference(s, SYSTEM, KEY)
                setup["profile"] = "other-private-profile"
                s.remember(SYSTEM, KEY, setup)
            return result

        with (
            patch.object(self.live, "_chores", return_value=self.chores),
            patch.object(self.chores, "claim_reminder", side_effect=acknowledge_then_rebind),
        ):
            self.live.delivered(offer, success=True)
        with self.live.store() as s:
            self.assertIsNone(preference(s, "other-private-profile", "conversation.chore_delivery"))

    def test_factual_revalidation_after_claim_rejects_completion_or_other_ack(self):
        offer = self.offer()
        self.assertTrue(self.live.claim(offer))
        self.assertTrue(self.live.revalidate_chore_offer(offer))
        self.chores.complete(self.item["id"])
        self.assertFalse(self.live.revalidate_chore_offer(offer))

    def test_accepting_a_chore_reminder_does_not_create_preference_confirmation(self):
        offer = self.offer()
        self.assertTrue(self.live.claim(offer))
        composer = Mock(
            return_value={
                "reply": "The tag or dashboard can mark it done.",
                "memory": {"field": "hobbies", "values": ["laundry"], "evidence": "sure"},
            }
        )
        reply = self.live.answer("sure", composer)
        self.assertEqual("The tag or dashboard can mark it done.", reply)
        self.assertIsNone(self.live.context()["pending"])
        self.assertTrue(self.chores.due())

    def test_model_gets_placeholder_only_and_unsafe_framing_falls_back(self):
        offer = self.offer()
        composer = Mock(
            return_value={"reply": "A tiny lab note: {chores}. No rush.", "memory": None}
        )
        result = self.live.opening(offer, composer)
        self.assertIn(self.item["title"], result["reply"])
        self.assertNotIn(self.item["title"], json.dumps(composer.call_args.args))
        bad = Mock(return_value={"reply": "You are lazy. {chores}", "memory": None})
        self.assertNotIn("lazy", self.live.opening(offer, bad)["reply"])
        self.assertTrue(self.chores.due(remind_only=True))


class MorningChoreTests(unittest.TestCase):
    def setUp(self):
        morning_fixtures.BriefingTests.setUp(self)
        self.chores = Chores(self.folder, clock=lambda: self.now)
        self.item = due_chore(self.folder, self.now)

    def summary(self):
        return self.briefing.enrich(self.morning.view("test-tv"))

    def test_cards_and_generation_do_not_claim_and_success_only_acknowledges(self):
        summary = self.summary()
        self.assertIn("chores", [c["kind"] for c in summary["cards"]])
        self.summary()
        self.assertTrue(self.chores.due(remind_only=True))
        composer = Mock(
            side_effect=lambda character, data: (
                "Good morning, {name}. "
                + " ".join("{" + k + "}." for k in data["tokens"] if k != "name")
            )
        )
        spoken, _, _ = self.briefing.message(summary, {"persona": "invented"}, composer)
        self.assertIn(self.item["title"], spoken)
        self.assertNotIn(self.item["title"], json.dumps(composer.call_args.args))
        self.assertTrue(self.chores.due(remind_only=True))
        self.briefing.complete(success=False)
        self.assertTrue(self.chores.due(remind_only=True))
        spoken, _, _ = self.briefing.message(summary, {"persona": "invented"})
        self.briefing.complete(success=True)
        self.assertEqual([], self.chores.due(remind_only=True))
        self.assertTrue(self.chores.due())

    def test_completed_chore_is_removed_from_pending_spoken_facts(self):
        spoken, _, _ = self.briefing.message(self.summary(), {"persona": "invented"})
        self.chores.complete(self.item["id"])
        self.assertNotIn(self.item["title"], self.briefing.revalidate_chores(spoken))
        self.briefing.complete(success=True)
        self.assertEqual([], self.chores.due())

    def test_pause_and_guest_hide_private_chore_cards(self):
        for flag in ("paused", "guest"):
            self.owner.control({flag: True})
            summary = self.briefing.enrich({"cards": []})
            self.assertNotIn("chores", [c["kind"] for c in summary["cards"]])
            self.owner.control({flag: False})

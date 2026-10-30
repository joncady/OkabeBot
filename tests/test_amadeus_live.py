"""Synthetic door/attention/reply flow; never records or actuates real hardware."""

import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock
from okabebot.amadeus_live import ProactiveConversation
from okabebot.amadeus_habits import preference
from okabebot.amadeus_onboarding import SYSTEM, KEY


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.now = datetime(2030, 1, 1, 18, tzinfo=timezone.utc).timestamp()
        self.live = ProactiveConversation(self.folder, lambda: self.now)
        with self.live.store() as s:
            s.remember(
                SYSTEM,
                KEY,
                dict(
                    profile="fiction",
                    sources=["door_presence"],
                    paused=False,
                    guest=False,
                    timezone="UTC",
                    quiet_start="23:00",
                    quiet_end="07:00",
                ),
            )
        (self.folder / "ha-bindings.json").write_text(
            json.dumps({"door": ["binary_sensor.invented"]})
        )
        with self.live.store() as s:
            s.remember("fiction", "conversation.memory_policy", {"auto_accept": False})
        self.live.configure(enabled=True, destination="desk")
        self.event = dict(
            entity_id="binary_sensor.invented",
            state="on",
            event_id="invented-event",
            observed_at=self.now,
        )
        self.args = dict(
            destination="desk", busy=False, focus=False, media=False, quiet=False, audio_ready=True
        )

    def attention(self, **kw):
        self.live.attention(
            dict(
                observed_at=self.now,
                dnd="off",
                dnd_reported_at=self.now,
                focus="off",
                media="clear",
                presence="unknown",
            )
            | kw
        )

    def ready(self):
        self.assertTrue(self.live.door(self.event))
        self.now += 1000
        self.attention()
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.attention()
        return self.live.check(**self.args)

    def test_first_door_and_restart_consume_before_speech(self):
        offer = self.ready()
        self.assertIsNotNone(offer)
        self.assertFalse(self.live.door(self.event | {"observed_at": self.now}))
        self.assertTrue(self.live.claim(offer))
        restarted = ProactiveConversation(self.folder, lambda: self.now)
        self.assertIsNone(restarted.check(**self.args))
        self.assertFalse(restarted.claim(offer))

    def test_protected_windows_reset_continuous_clear_period(self):
        self.ready()
        for name in ("busy", "focus", "media", "quiet"):
            self.assertIsNone(self.live.check(**(self.args | {name: True})))
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.attention()
        self.assertIsNotNone(self.live.check(**self.args))
        self.attention(dnd="on")
        self.assertIsNone(self.live.check(**self.args))

    def test_stale_unknown_and_wrong_destination_fail_closed(self):
        self.ready()
        self.assertIsNone(self.live.check(**(self.args | {"destination": "other"})))
        self.attention(media="unknown")
        self.assertIsNone(self.live.check(**self.args))
        self.attention(dnd_reported_at=self.now - 1801)
        with self.live.store() as store:
            gate = preference(store, "fiction", "conversation.attention")
            self.assertEqual(gate["dnd"], "unknown")
            self.assertEqual(gate["observed_at"], self.now)
        self.assertIsNone(self.live.check(**self.args))
        self.now += 151
        self.assertIsNone(self.live.check(**self.args))

    def test_pause_guest_quiet_and_expired_window(self):
        self.ready()
        with self.live.store() as s:
            setup = preference(s, SYSTEM, KEY)
            setup["guest"] = True
            s.remember(SYSTEM, KEY, setup)
        self.assertIsNone(self.live.check(**self.args))
        self.assertFalse(self.live.claim({"day": "2030-01-01"}))
        self.assertIsNone(self.live.context())

    def test_preference_requires_explicit_separate_confirmation(self):
        offer = self.ready()
        self.live.claim(offer)
        generate = Mock(
            return_value={
                "reply": "Mysteries are fun.",
                "memory": {
                    "field": "genres",
                    "values": ["mystery"],
                    "evidence": "usually enjoy mysteries",
                },
            }
        )
        reply = self.live.answer("I usually enjoy mysteries.", generate)
        self.assertIn("remember", reply)
        with self.live.store() as s:
            self.assertEqual(preference(s, "fiction", "context.preferences", {}), {})
        self.live.answer("yes please", generate)
        with self.live.store() as s:
            self.assertEqual(
                preference(s, "fiction", "context.preferences")["media"]["genres"], ["mystery"]
            )
        self.assertEqual(generate.call_count, 1)
        self.assertIsNone(self.live.context())

    def test_decline_stop_and_unsubstantiated_model_memory(self):
        self.live.claim(self.ready())
        generate = Mock(
            return_value={
                "reply": "Okay",
                "memory": {"field": "genres", "values": ["horror"], "evidence": "not in input"},
            }
        )
        self.assertEqual(self.live.answer("Something light tonight", generate), "Okay")
        self.assertIsNone(self.live.context()["pending"])
        self.live.answer("don't ask again", generate)
        self.assertFalse(self.live.enabled())
        self.assertIsNone(self.live.context())

    def test_snapshot_or_unbound_door_does_not_arm(self):
        for value in (
            {"event_id": "snapshot:invented"},
            {"entity_id": "binary_sensor.other"},
            {"state": "off"},
        ):
            self.assertFalse(self.live.door(self.event | value))

    def test_interest_reply_is_not_routed_as_media_control(self):
        from okabebot.local_conversation import preference_device_request

        specs = {"get_current_media": {}, "control_spotify": {}}
        self.assertFalse(preference_device_request("I usually enjoy watching mysteries", specs))
        self.assertTrue(preference_device_request("What is playing on TV?", specs))
        self.assertTrue(preference_device_request("Pause Spotify", specs))

    def test_proactive_audio_cannot_fallback_or_follow_a_location_change(self):
        from types import SimpleNamespace
        from okabebot.application import Application

        surface = {
            "current_location": "desk",
            "locations": [{"id": "desk", "adapter": "pi", "approved": True}],
        }
        controller = SimpleNamespace(proactive=self.live, surfaces=Mock())
        controller.surfaces.snapshot.return_value = surface
        app = Application(controller)
        self.assertEqual(app.execute("/audio/resolve", {"purpose": "proactive"}), {"target": "pi"})
        surface["current_location"] = "other"
        with self.assertRaises(ValueError):
            app.execute("/audio/resolve", {"purpose": "proactive"})

    def test_fake_button_reply_uses_real_transcript_confirmation_path(self):
        import base64
        import sqlite3
        from okabebot.bridge import Bridge

        self.live.claim(self.ready())
        bridge = Bridge.__new__(Bridge)
        bridge.folder = self.folder / "ptt"
        bridge.folder.mkdir()
        with sqlite3.connect(bridge.folder / "clips.sqlite3") as db:
            db.execute("CREATE TABLE clips (id TEXT PRIMARY KEY,status TEXT,transcript TEXT)")
        bridge.proactive = self.live
        bridge.codex = Mock()
        bridge.codex.specs = {}
        bridge.codex.text_turn.return_value = {"conversation": True, "reply": "", "tools": []}
        bridge.codex.compose_preference.return_value = {
            "reply": "That sounds fun.",
            "memory": {
                "field": "hobbies",
                "values": ["gardening"],
                "evidence": "usually enjoy gardening",
            },
        }
        bridge.notify = Mock()
        bridge.show_activity = Mock()
        bridge.reply = Mock()
        bridge.transcribe = Mock(return_value="I usually enjoy gardening")
        clip = {
            "clip_id": "invented-button-1",
            "wav_base64": base64.b64encode(b"invented").decode(),
        }
        self.assertTrue(bridge._handle_clip(clip))
        self.assertIn("remember", bridge.reply.call_args.args[0])
        bridge.transcribe.return_value = "yes please"
        self.assertTrue(bridge._handle_clip(clip | {"clip_id": "invented-button-2"}))
        bridge.codex.submit.assert_not_called()
        with self.live.store() as s:
            self.assertEqual(
                preference(s, "fiction", "context.preferences")["hobbies"], ["gardening"]
            )

    def test_live_learning_adds_to_existing_interests(self):
        with self.live.store() as s:
            s.remember("fiction", "context.preferences", {"hobbies": ["drawing"]})
        self.live.claim(self.ready())
        self.live.answer(
            "I usually enjoy gardening",
            lambda *_: {
                "reply": "Okay",
                "memory": {
                    "field": "hobbies",
                    "values": ["gardening"],
                    "evidence": "usually enjoy gardening",
                },
            },
        )
        self.live.answer("yes please", Mock())
        with self.live.store() as s:
            self.assertEqual(
                preference(s, "fiction", "context.preferences")["hobbies"], ["drawing", "gardening"]
            )

    def test_unconfirmed_evidence_is_not_retained_and_session_expires(self):
        self.live.claim(self.ready())
        self.live.answer(
            "I usually enjoy gardening",
            lambda *_: {
                "reply": "Okay",
                "memory": {
                    "field": "hobbies",
                    "values": ["gardening"],
                    "evidence": "usually enjoy gardening",
                },
            },
        )
        self.assertNotIn("evidence", self.live.context()["pending"])
        self.now += 601
        self.assertIsNone(self.live.context())
        with self.live.store() as s:
            from okabebot.amadeus_live import STATE

            self.assertIsNone(preference(s, "fiction", STATE)["pending"])
            self.assertEqual(preference(s, "fiction", "context.preferences", {}), {})

    def test_unsupported_memory_annotation_preserves_chat_without_writing(self):
        self.live.claim(self.ready())
        for invalid in (
            {
                "field": "preferences",
                "values": ["invented taste"],
                "evidence": "generally prefer tart apples",
            },
            {"field": [], "values": ["invented taste"], "evidence": "generally prefer tart apples"},
            {"field": "food_drink", "values": ["tart apples"], "evidence": "fabricated quotation"},
        ):
            reply = self.live.answer(
                "I generally prefer tart apples",
                lambda *_: {"reply": "Do you enjoy them baked too?", "memory": invalid},
            )
            self.assertEqual(reply, "Do you enjoy them baked too?")
            self.assertIsNotNone(self.live.context())
            self.assertIsNone(self.live.context()["pending"])
        with self.live.store() as s:
            self.assertEqual(preference(s, "fiction", "context.preferences", {}), {})

    def test_food_taste_uses_explicit_confirmation_and_does_not_become_media_genre(self):
        self.live.claim(self.ready())
        reply = self.live.answer(
            "I generally prefer tart apples",
            lambda *_: {
                "reply": "Lovely.",
                "memory": {
                    "field": "food_drink",
                    "values": ["tart apples"],
                    "evidence": "generally prefer tart apples",
                },
            },
        )
        self.assertIn("remember that you prefer tart apples", reply)
        with self.live.store() as s:
            self.assertEqual(preference(s, "fiction", "context.preferences", {}), {})
        self.live.answer("yes please", Mock())
        with self.live.store() as s:
            value = preference(s, "fiction", "context.preferences")
            self.assertEqual(value, {"food_drink": ["tart apples"]})

    def test_explicit_reply_resume_does_not_rearm_or_replay_the_invitation(self):
        self.live.claim(self.ready())
        self.live.end()
        result = self.live.resume_reply()
        self.assertFalse(result["invitation_replayed"])
        self.assertIsNotNone(self.live.context())
        self.assertIsNone(self.live.check(**self.args))
        self.now += 7 * 3600
        with self.assertRaises(ValueError):
            self.live.resume_reply()

    def test_natural_affirmative_saves_the_pending_meaning_once_without_generation(self):
        self.live.claim(self.ready())
        self.live.answer(
            "I enjoy playing the cello",
            lambda *_: {
                "reply": "Lovely.",
                "memory": {
                    "field": "hobbies",
                    "values": ["cello"],
                    "evidence": "enjoy playing the cello",
                },
            },
        )
        generate = Mock(side_effect=AssertionError("Confirmation must not require generation"))
        result = self.live.answer(
            "Absolutely, please keep that in mind for future suggestions.", generate
        )
        self.assertIn("Remembered", result)
        generate.assert_not_called()
        with self.live.store() as s:
            self.assertEqual(
                preference(s, "fiction", "context.preferences"), {"hobbies": ["cello"]}
            )
        self.assertIsNone(self.live.context())

    def test_confirmation_phrases_do_not_accept_conditions_corrections_or_uncertainty(self):
        from okabebot.amadeus_live import confirmation_answer

        for text in (
            "Yes, please keep that in mind.",
            "Sure. Save that for later.",
            "Absolutely, go ahead.",
            "Yes I would like that.",
        ):
            self.assertIs(confirmation_answer(text), True)
        for text in (
            "Yes, but just for this weekend.",
            "Sure, if I still like it next week.",
            "Yes, actually I meant something different.",
            "Not sure.",
            "Sure?",
            "Maybe yes.",
            "Yes, no, wait.",
        ):
            self.assertIsNone(confirmation_answer(text))
        self.assertIs(confirmation_answer("No thanks."), False)

    def test_watch_context_overrides_phone_and_unknown_blocks_delivery(self):
        self.assertIsNotNone(self.ready())
        self.live.presence_provider = lambda: {
            "configured": True,
            "fresh": False,
            "presence": "home",
            "healthy_scanners": 2,
        }
        self.assertIsNone(self.live.check(**self.args))
        self.live.presence_provider = lambda: {
            "configured": True,
            "fresh": True,
            "presence": "home",
            "healthy_scanners": 2,
        }
        self.attention(presence="away")
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.attention(presence="away")
        self.assertIsNotNone(self.live.check(**self.args))

    def test_dnd_can_be_ignored_without_disabling_other_attention_gates(self):
        self.assertIsNotNone(self.ready())
        self.attention(dnd="unknown", dnd_reported_at=0)
        self.assertIsNone(self.live.check(**self.args))
        self.live.interruptions({"respect_dnd": False})
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        self.attention(dnd="unknown", dnd_reported_at=0)
        self.assertIsNotNone(self.live.check(**self.args))
        self.assertIsNone(self.live.check(**{**self.args, "focus": True}))
        self.assertIsNone(self.live.check(**{**self.args, "media": True}))
        self.assertIsNone(self.live.check(**{**self.args, "quiet": True}))
        self.assertFalse(self.live.interruptions()["respect_dnd"])
        with self.assertRaises(ValueError):
            self.live.interruptions({"respect_dnd": "false"})

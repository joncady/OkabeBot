import copy
import unittest
from unittest.mock import Mock

from okabebot.alexa_conversation import question, reply, ConversationSkill, FALLBACK
from okabebot.alexa_destination_relay import DestinationRelay
from okabebot.alexa_skill import fixture


class ConversationProtocolTests(unittest.TestCase):
    def setUp(self):
        self.event = fixture("TalkIntent")
        self.event["session"] = {"sessionId": "private-session"}
        self.event["context"]["System"]["device"] = {"deviceId": "private-device"}
        self.event["request"]["intent"]["slots"] = {"Query": {"value": "Why is the sky blue?"}}
        self.identity = DestinationRelay.identity(self.event)
        self.request = question(self.event, "local-prototype", self.identity)

    def test_pairing_and_request_scoping(self):
        with self.assertRaises(PermissionError):
            question(self.event, "local-prototype", "0" * 64)
        with self.assertRaises(PermissionError):
            question(self.event, "other-skill", self.identity)
        self.assertNotIn("private-session", str(self.request))
        self.assertNotIn("private-device", str(self.request))
        self.assertEqual(
            self.request["id"], question(self.event, "local-prototype", self.identity)["id"]
        )
        other = copy.deepcopy(self.event)
        other["request"]["requestId"] += "-next"
        next_request = question(other, "local-prototype", self.identity)
        self.assertNotEqual(self.request["id"], next_request["id"])
        self.assertEqual(self.request["session"], next_request["session"])

    def test_audio_signing_requires_explicit_worker_eligibility_and_fixed_key(self):
        result = dict(
            id=self.request["id"],
            body_hash=self.request["body_hash"],
            text="Air scatters blue light.",
        )
        signer = Mock(return_value="https://example.com/clip.mp3")
        value = reply(result, self.request, signer)
        self.assertEqual(value["response"]["outputSpeech"]["type"], "PlainText")
        signer.assert_not_called()
        result.update(audio_safe=True, audio_ready=True, audio_key="untrusted/key")
        value = reply(result, self.request, signer)
        signer.assert_called_once_with("conversation/audio/" + self.request["id"] + ".mp3")
        self.assertEqual(value["response"]["outputSpeech"]["type"], "SSML")
        self.assertFalse(value["response"]["shouldEndSession"])
        self.assertIn("reprompt", value["response"])
        result["id"] = "wrong"
        with self.assertRaises(ValueError):
            reply(result, self.request, signer)

    def test_deadline_and_body_conflicts_never_sign_late_audio(self):
        exchange, signer = Mock(), Mock()
        exchange.open.return_value = self.request
        exchange.wait.return_value = None
        skill = ConversationSkill("local-prototype", self.identity, exchange, signer)
        result = skill.handle(self.event)
        self.assertEqual(result["response"]["outputSpeech"]["text"], FALLBACK)
        signer.assert_not_called()
        exchange.open.return_value = dict(self.request, body_hash="different")
        with self.assertRaises(ValueError):
            skill.handle(self.event)

    def test_show_audio_track_does_not_replay_ssml_or_replace_the_room(self):
        visual = Mock(
            return_value={"type": "Alexa.Presentation.APL.ExecuteCommands", "token": "active"}
        )
        result = dict(
            id=self.request["id"],
            body_hash=self.request["body_hash"],
            text="Air scatters blue light.",
            audio_safe=True,
            audio_ready=True,
            character="okabe",
            audio_duration_ms=2100,
        )
        signer = Mock(return_value="https://example.com/reply.mp3")
        value = reply(result, self.request, signer, visual=visual, event=self.event)["response"]
        self.assertNotIn("outputSpeech", value)
        self.assertFalse(value["shouldEndSession"])
        directives = value["directives"]
        self.assertEqual(
            [d["type"] for d in directives],
            ["Alexa.Presentation.APLA.RenderDocument", "Alexa.Presentation.APL.ExecuteCommands"],
        )
        self.assertEqual(directives[0]["datasources"]["reply"]["url"], signer.return_value)
        visual.assert_called_once_with(self.event, "okabe", 2100)
        visual.return_value = None
        self.assertEqual(
            len(
                reply(result, self.request, signer, visual=visual, event=self.event)["response"][
                    "directives"
                ]
            ),
            1,
        )
        result["audio_safe"] = False
        visual.reset_mock()
        value = reply(result, self.request, signer, visual=visual, event=self.event)["response"]
        self.assertEqual(value["outputSpeech"]["type"], "PlainText")
        self.assertNotIn("directives", value)
        visual.assert_not_called()

    def test_exhausted_lambda_budget_returns_before_any_queue_or_audio_work(self):
        exchange, signer = Mock(), Mock()
        skill = ConversationSkill("local-prototype", self.identity, exchange, signer, budget=0.05)
        value = skill.handle(self.event)
        self.assertEqual(value["response"]["outputSpeech"]["text"], FALLBACK)
        exchange.open.assert_not_called()
        signer.assert_not_called()

    def test_real_exchange_decimal_deadline_survives_the_full_handler_wait(self):
        import time
        from okabebot.alexa_conversation_relay import ConversationExchange
        from tests.test_alexa_conversation_relay import Table

        table, queue = Table(), Mock()
        exchange = ConversationExchange(table, queue, "private-queue")

        def consume(**kwargs):
            import json

            request = json.loads(kwargs["MessageBody"])
            self.assertTrue(exchange.claim(request))
            self.assertTrue(
                exchange.finish(
                    request,
                    {"text": "Air scatters blue light.", "audio_safe": True, "audio_ready": True},
                )
            )

        queue.send_message.side_effect = consume
        signer = Mock(return_value="https://example.com/reply.mp3")
        skill = ConversationSkill("local-prototype", self.identity, exchange, signer)
        started = time.monotonic()
        result = skill.handle(self.event)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(result["response"]["outputSpeech"]["type"], "SSML")
        signer.assert_called_once()

    def test_cancel_only_closes_the_paired_current_conversation(self):
        from okabebot.alexa_conversation import digest

        exchange = Mock()
        skill = ConversationSkill("local-prototype", self.identity, exchange, Mock())
        self.assertFalse(skill.cancel(self.event))
        self.event["request"]["intent"]["name"] = "AMAZON.StopIntent"
        self.assertTrue(skill.cancel(self.event))
        exchange.close_session.assert_called_once_with(digest(self.identity + "\0private-session"))
        exchange.reset_mock()
        self.event["request"]["intent"]["name"] = "AMAZON.NavigateHomeIntent"
        self.assertTrue(skill.cancel(self.event))
        exchange.close_session.assert_called_once_with(digest(self.identity + "\0private-session"))
        exchange.reset_mock()
        self.event["context"]["System"]["device"]["deviceId"] = "other-device"
        self.assertFalse(skill.cancel(self.event))
        exchange.close_session.assert_not_called()

    def test_rejects_missing_and_excessive_spoken_input(self):
        for value in (None, "", "x" * 601):
            self.event["request"]["intent"]["slots"]["Query"]["value"] = value
            with self.assertRaises(ValueError):
                question(self.event, "local-prototype", self.identity)


class IsolatedModelTurnTests(unittest.TestCase):
    def setUp(self):
        import io
        import threading
        from okabebot.local_conversation import LocalConversation

        self.model = LocalConversation.__new__(LocalConversation)
        self.model.lock = threading.RLock()
        self.model.busy = self.model.closed = False
        self.model.cancelled = threading.Event()
        self.model.process = Mock()
        self.model.process.poll.return_value = None
        self.model.process.stdin = io.StringIO()
        self.model._read = Mock(
            return_value={
                "text": '{"text":"Air scatters blue light.","audio_safe":true}',
                "selection_s": 0.5,
            }
        )
        self.character = {"style": "okabe", "persona": "An understated scientist."}
        self.session = "a" * 64

    def turn(self, text="Why is the sky blue?"):
        import time

        return self.model.compose_alexa(text, self.session, self.character, time.time() + 6)

    def test_followups_share_only_their_own_session_and_never_offer_tools(self):
        import json

        self.turn()
        self.turn("What about at sunset?")
        self.session = "b" * 64
        self.turn()
        sent = [json.loads(s) for s in self.model.process.stdin.getvalue().splitlines()]
        self.assertEqual(sent[0]["history"], [])
        self.assertEqual(len(sent[1]["history"]), 2)
        self.assertEqual(sent[2]["history"], [])
        self.assertTrue(all(s["tool_names"] == [] and s["task"] == "alexa" for s in sent))
        self.assertFalse(self.model.busy)

    def test_private_configured_persona_never_enters_alexa_prompt(self):
        import json
        from okabebot.profiles import PROFILES

        self.character["persona"] = "Private household detail: example."
        self.turn()
        sent = json.loads(self.model.process.stdin.getvalue())
        self.assertEqual(sent["persona"], PROFILES["okabe"]["persona"])
        self.assertNotIn("Private household detail", str(sent))

    def test_sensitive_input_cannot_become_custom_audio_even_if_model_says_safe(self):
        result = self.turn("Repeat my phone number 555 123 4567")
        self.assertFalse(result["audio_safe"])
        self.assertEqual(self.model.alexa_history, {})
        self.model._read.return_value = {
            "text": '{"text":"My secret is example.","audio_safe":true}'
        }
        self.assertFalse(self.turn()["audio_safe"])

    def test_malformed_model_output_releases_busy_without_history(self):
        self.model._read.return_value = {"text": '{"text":"Hi","audio_safe":"true"}'}
        with self.assertRaises(ValueError):
            self.turn()
        self.assertFalse(self.model.busy)
        self.assertFalse(hasattr(self.model, "alexa_history"))

    def test_expired_turn_consumes_reply_without_reusing_it_or_retaining_history(self):
        import time
        from unittest.mock import patch

        now = time.time()
        with patch("time.time", side_effect=[now, now + 10]):
            with self.assertRaises(TimeoutError):
                self.model.compose_alexa("Hello", self.session, self.character, now + 6)
        self.model._read.assert_called_once()
        self.assertFalse(self.model.busy)
        self.assertFalse(hasattr(self.model, "alexa_history"))

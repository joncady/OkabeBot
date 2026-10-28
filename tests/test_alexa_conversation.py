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

import copy
import unittest
from unittest.mock import Mock

from okabebot.alexa_skill import fixture, response
from okabebot.alexa_visuals import attach_character, FRAME_NAMES


class AplCharacterTests(unittest.TestCase):
    def event(self):
        event = fixture("VoiceDemoIntent")
        event["context"]["System"]["device"] = {
            "supportedInterfaces": {"Alexa.Presentation.APL": {}}
        }
        return event

    def test_audio_only_echo_is_unchanged_and_does_not_sign_images(self):
        result = response("demo")
        before = copy.deepcopy(result)
        signer = Mock()
        self.assertEqual(attach_character(result, fixture(), signer), before)
        signer.assert_not_called()

    def test_screen_uses_bounded_speaking_and_blinking_without_opening_mic(self):
        frames = ["https://example.com/" + name for name in FRAME_NAMES]
        result = attach_character(response("demo", end=False), self.event(), lambda: frames)
        self.assertNotIn("shouldEndSession", result["response"])
        self.assertNotIn("reprompt", result["response"])
        directive = result["response"]["directives"][0]
        self.assertEqual(directive["type"], "Alexa.Presentation.APL.RenderDocument")
        self.assertEqual(directive["datasources"]["scene"]["frames"], frames)
        component = directive["document"]["mainTemplate"]["items"][0]
        self.assertEqual(component["id"], "lab")
        sequences = component["onMount"][0]["commands"]
        self.assertTrue(all(0 <= s["repeatCount"] < 30 for s in sequences))
        # No SendEvent, speech command, tool or background network polling loop.
        allowed = {"Sequential", "Idle", "SetValue"}
        for sequence in sequences:
            self.assertTrue(all(c["type"] in allowed for c in sequence["commands"]))

    def test_rejects_missing_or_insecure_assets(self):
        for frames in ([], ["https://example.com/x"] * 3, ["http://example.com/x"] * 4):
            with self.assertRaises(ValueError):
                attach_character(response("demo"), self.event(), lambda: frames)

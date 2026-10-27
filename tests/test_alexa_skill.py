import copy
import unittest

from okabebot.alexa_skill import Prototype, fixture, response


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.skill = Prototype(
            "local-prototype",
            "local-test-user",
            {
                "get_device_health": lambda: self.calls.append("health"),
                "get_companion_locations": lambda: {
                    "locations": [{"name": "Desk"}, {"name": "Pending", "approved": False}]
                },
            },
        )

    def test_read_tools_and_replay(self):
        event = fixture()
        result = self.skill.handle(event)
        self.assertEqual(result, self.skill.handle(event))
        self.assertEqual(self.calls, ["health"])
        self.assertEqual(result["response"]["outputSpeech"]["type"], "PlainText")
        text = self.skill.handle(fixture("LabLocationsIntent"))["response"]["outputSpeech"]["text"]
        self.assertIn("Desk", text)
        self.assertNotIn("Pending", text)

    def test_account_and_time_guards(self):
        event = fixture()
        for key in ("application", "user"):
            bad = copy.deepcopy(event)
            field = "applicationId" if key == "application" else "userId"
            bad["context"]["System"][key][field] = "other"
            with self.assertRaises(PermissionError):
                self.skill.handle(bad)
        event["request"]["timestamp"] = "2000-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            self.skill.handle(event)
        self.assertEqual(self.calls, [])

    def test_unknown_never_executes(self):
        self.skill.handle(fixture("PressEverythingIntent"))
        self.assertEqual(self.calls, [])

    def test_generic_audio_only(self):
        self.skill.audio_url = "https://example.com/demo.mp3?a=1&b=2"
        ssml = self.skill.handle(fixture("VoiceDemoIntent"))["response"]["outputSpeech"]["ssml"]
        self.assertIn("&amp;", ssml)
        self.assertNotIn("audio", self.skill.handle(fixture())["response"]["outputSpeech"])
        with self.assertRaises(ValueError):
            response("", audio_url="http://example.com/demo.mp3")

    def test_session_lifecycle(self):
        event = fixture()
        event["request"]["type"] = "LaunchRequest"
        result = self.skill.handle(event)
        self.assertFalse(result["response"]["shouldEndSession"])
        self.assertIn("reprompt", result["response"])
        event = fixture()
        event["request"]["type"] = "SessionEndedRequest"
        self.assertEqual(self.skill.handle(event)["response"], {})

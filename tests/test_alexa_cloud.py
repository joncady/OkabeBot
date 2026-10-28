import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from okabebot.alexa_skill import fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alexa_cloud", ROOT / "infra/aws/alexa_skill.py")
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class CloudSkillTests(unittest.TestCase):
    def test_demo_and_launch_only_use_fixed_audio(self):
        audio = Mock(return_value="https://example.com/generic/demo.mp3?x=1&y=2")
        event = fixture("VoiceDemoIntent")
        event["request"]["intent"]["slots"] = {"url": {"value": "https://evil.invalid/"}}
        result = cloud.handle(event, "local-prototype", audio)
        self.assertIn("&amp;", result["response"]["outputSpeech"]["ssml"])
        self.assertNotIn("evil", json.dumps(result))
        event["request"]["type"] = "LaunchRequest"
        self.assertFalse(
            cloud.handle(event, "local-prototype", audio)["response"]["shouldEndSession"]
        )

    def test_local_tools_are_not_claimed_or_called(self):
        audio = Mock()
        for name in ("LabStatusIntent", "LabLocationsIntent", "AMAZON.StopIntent", "Other"):
            result = cloud.handle(fixture(name), "local-prototype", audio)
            self.assertEqual(result["response"]["outputSpeech"]["type"], "PlainText")
        audio.assert_not_called()

    def test_auth_and_time_before_audio(self):
        audio = Mock()
        event = fixture()
        with self.assertRaises(PermissionError):
            cloud.handle(event, "other-skill", audio)
        mismatch = copy.deepcopy(event)
        mismatch["session"] = {"application": {"applicationId": "other-skill"}}
        with self.assertRaises(PermissionError):
            cloud.handle(mismatch, "local-prototype", audio)
        event["request"]["timestamp"] = "2001-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            cloud.handle(event, "local-prototype", audio)
        audio.assert_not_called()

    def test_template_scopes_access_and_has_no_public_listener(self):
        resources = json.loads((ROOT / "infra/aws/alexa-skill.json").read_text())["Resources"]
        permission = resources["AlexaPermission"]["Properties"]
        self.assertEqual(permission["Principal"], "alexa-appkit.amazon.com")
        self.assertEqual(permission["EventSourceToken"], {"Ref": "SkillId"})
        self.assertFalse(any(r["Type"] == "AWS::Lambda::Url" for r in resources.values()))
        block = resources["Audio"]["Properties"]["PublicAccessBlockConfiguration"]
        self.assertTrue(all(block.values()))
        policy = resources["Role"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
        self.assertEqual(policy[0]["Action"], "s3:GetObject")
        keys = [entry["Fn::Sub"] for entry in policy[0]["Resource"]]
        self.assertEqual(len(keys), 5)
        self.assertTrue(keys[0].endswith("/generic/demo.mp3"))
        self.assertFalse(any("*" in key for key in keys))

    def test_inline_deployment_matches_source(self):
        spec = importlib.util.spec_from_file_location(
            "deploy_alexa", ROOT / "scripts/deploy-alexa-skill.py"
        )
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)
        source = deploy.template()["Resources"]["Skill"]["Properties"]["Code"]["ZipFile"]
        namespace = {}
        exec(compile(source, "index.py", "exec"), namespace)
        actual = namespace["handle"](
            fixture("VoiceDemoIntent"), "local-prototype", lambda: "https://example.com/demo.mp3"
        )
        self.assertEqual(actual["response"]["outputSpeech"]["type"], "SSML")

    def test_mount_diagnostic_is_bounded_silent_and_has_no_asset_or_tool_effect(self):
        audio, frames = Mock(), Mock()
        event = fixture()
        event["request"].update(
            type="Alexa.Presentation.APL.UserEvent",
            token="little-lab-character",
            arguments=["little-lab-mounted"],
            source={"handler": "Mount"},
        )
        with self.assertLogs(cloud.__name__, level="WARNING") as logs:
            result = cloud.handle(event, "local-prototype", audio, frames)
        self.assertEqual(result, {"version": "1.0", "response": {}})
        self.assertEqual(logs.output, ["WARNING:alexa_cloud:little_lab_visual document=mounted"])
        audio.assert_not_called()
        frames.assert_not_called()
        for field, value in (
            ("token", "old-document"),
            ("arguments", ["arbitrary-tool"]),
            ("source", {"handler": "Press"}),
        ):
            invalid = copy.deepcopy(event)
            invalid["request"][field] = value
            with self.assertRaises(ValueError):
                cloud.handle(invalid, "local-prototype", audio, frames)

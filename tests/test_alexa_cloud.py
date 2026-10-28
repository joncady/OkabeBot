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

    def test_destination_is_opt_in_and_validated_before_relay(self):
        relay = Mock()
        audio = Mock()
        event = fixture("VisitIntent")
        result = cloud.handle(event, "local-prototype", audio)
        self.assertIn("not enabled", result["response"]["outputSpeech"]["text"])
        audio.assert_not_called()
        relay.launch.return_value = {"version": "1.0", "response": {}}
        audio_only = cloud.handle(event, "local-prototype", audio, destination=relay)
        self.assertIn("screen-capable", audio_only["response"]["outputSpeech"]["text"])
        relay.launch.assert_not_called()
        event["context"]["System"]["device"] = {
            "supportedInterfaces": {"Alexa.Presentation.APL": {}}
        }
        self.assertEqual(
            cloud.handle(event, "local-prototype", audio, destination=relay),
            relay.launch.return_value,
        )
        relay.launch.assert_called_once_with(event)
        with self.assertRaises(PermissionError):
            cloud.handle(event, "wrong-skill", audio, destination=relay)
        self.assertEqual(relay.launch.call_count, 1)

    def test_destination_iam_is_disabled_by_default_and_cannot_write_commands(self):
        value = json.loads((ROOT / "infra/aws/alexa-skill.json").read_text())
        self.assertEqual(value["Parameters"]["EnableDestination"]["Default"], "false")
        policy = value["Resources"]["DestinationPolicy"]
        self.assertEqual(policy["Condition"], "DestinationEnabled")
        statements = policy["Properties"]["PolicyDocument"]["Statement"]
        self.assertEqual(statements[0]["Resource"]["Fn::Sub"], "${Audio.Arn}/surface/session.json")
        self.assertEqual(statements[1]["Action"], "s3:GetObject")
        self.assertTrue(all("*" not in r["Fn::Sub"] for r in statements[1]["Resource"]))

    def test_opt_in_inline_handler_packages_and_signs_only_fixed_layers(self):
        import os
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location(
            "destination_deploy", ROOT / "scripts/deploy-alexa-skill.py"
        )
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)
        source = deploy.template()["Resources"]["Skill"]["Properties"]["Code"]["ZipFile"]
        self.assertNotIn("from okabebot.", source)
        self.assertNotIn("from .alexa_destination", source)
        namespace = {}
        exec(compile(source, "index.py", "exec"), namespace)
        client = Mock()
        missing = RuntimeError("missing object")
        missing.response = {"Error": {"Code": "NoSuchKey"}}
        client.get_object.side_effect = missing
        client.generate_presigned_url.return_value = "https://example.com/signed.png"
        boto = Mock()
        boto.client.return_value = client
        config = Mock()
        event = fixture("VisitIntent")
        event["context"]["System"]["device"] = {
            "deviceId": "test-screen",
            "supportedInterfaces": {"Alexa.Presentation.APL": {}},
        }
        with (
            patch.dict(
                "sys.modules", {"boto3": boto, "botocore": Mock(), "botocore.config": config}
            ),
            patch.dict(
                os.environ,
                {
                    "SKILL_ID": "local-prototype",
                    "AUDIO_BUCKET": "test-private",
                    "DESTINATION_ENABLED": "true",
                    "DESTINATION_CHARACTER": "okabe",
                    "DESTINATION_SET": "maid-cafe",
                },
            ),
        ):
            result = namespace["handler"](event, None)
        self.assertEqual(
            result["response"]["directives"][0]["type"], "Alexa.Presentation.APL.RenderDocument"
        )
        self.assertNotIn("outputSpeech", result["response"])
        keys = [
            call.kwargs["Params"]["Key"] for call in client.generate_presigned_url.call_args_list
        ]
        self.assertEqual(
            keys,
            [
                "surface/assets/background.png",
                "surface/assets/actor-idle.png",
                "surface/assets/actor-talk-a.png",
                "surface/assets/actor-talk-b.png",
                "surface/assets/actor-blink.png",
            ],
        )
        client.put_object.assert_called_once()
        self.assertEqual(client.put_object.call_args.kwargs["Key"], "surface/session.json")
        session = json.loads(client.put_object.call_args.kwargs["Body"])
        self.assertFalse(session["ready"])
        self.assertEqual(session["painted"], "hidden")

    def test_relay_bootstrap_preserves_existing_state_without_list_permission(self):
        import subprocess

        spec = importlib.util.spec_from_file_location(
            "bootstrap_deploy", ROOT / "scripts/deploy-alexa-skill.py"
        )
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)
        calls = []

        def aws(*args):
            calls.append(args)
            self.assertEqual(Path(args[args.index("--body") + 1]).read_text(), "{}")
            self.assertEqual(args[args.index("--if-none-match") + 1], "*")

        deploy.bootstrap_destination(aws, "private-test")
        self.assertEqual(
            [a[a.index("--key") + 1] for a in calls],
            ["surface/session.json", "surface/command.json"],
        )
        existing = Mock(
            side_effect=subprocess.CalledProcessError(1, ["aws"], stderr="PreconditionFailed")
        )
        deploy.bootstrap_destination(existing, "private-test")
        self.assertEqual(existing.call_count, 2)
        conflict = subprocess.CalledProcessError(1, ["aws"], stderr="ConditionalRequestConflict")
        retry = Mock(side_effect=[conflict, None, None])
        deploy.bootstrap_destination(retry, "private-test")
        self.assertEqual(retry.call_count, 3)
        denied = Mock(side_effect=subprocess.CalledProcessError(1, ["aws"], stderr="AccessDenied"))
        with self.assertRaises(subprocess.CalledProcessError):
            deploy.bootstrap_destination(denied, "private-test")
        self.assertEqual(denied.call_count, 1)

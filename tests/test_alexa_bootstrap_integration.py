"""Fresh deployment -> scoped store reads, with no AWS calls or bucket-list access."""

import hashlib
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from okabebot.alexa_destination_relay import PrivateDestinationStore


class BootstrapIntegrationTests(unittest.TestCase):
    def test_real_deploy_entrypoint_seeds_objects_before_publishing_worker_metadata(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "bootstrap_integration", root / "scripts/deploy-alexa-skill.py"
        )
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)
        objects = {}

        def run(command, **kwargs):
            if command[0] != "aws":
                raise AssertionError("Unexpected process")
            result = "{}"
            if "describe-stacks" in command:
                result = json.dumps(
                    {
                        "Stacks": [
                            {
                                "Outputs": [
                                    {"OutputKey": "AudioBucket", "OutputValue": "test-private"}
                                ]
                            }
                        ]
                    }
                )
            if "put-object" in command:
                key = command[command.index("--key") + 1]
                if "--if-none-match" in command and key in objects:
                    raise subprocess.CalledProcessError(1, command, stderr="PreconditionFailed")
                objects[key] = Path(command[command.index("--body") + 1]).read_bytes()
            return subprocess.CompletedProcess(command, 0, stdout=result, stderr="")

        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            audio = folder / "demo.mp3"
            audio.write_bytes(b"x" * 200)
            visuals = folder / "visuals"
            visuals.mkdir()
            for name in (
                "background.png",
                "actor-idle.png",
                "actor-talk-a.png",
                "actor-talk-b.png",
                "actor-blink.png",
            ):
                Image.new("RGBA", (960, 540), (0, 0, 0, 0)).save(visuals / name)
            Image.new("RGB", (960, 540), "black").save(visuals / "background.png")
            (visuals / "scene.json").write_text(
                json.dumps({"character": "okabe", "set": "maid-cafe"})
            )
            metadata = folder / "deployment.json"
            args = [
                "deploy",
                "--skill-id",
                "amzn1.ask.skill.example",
                "--audio",
                str(audio),
                "--destination-visuals",
                str(visuals),
                "--output",
                str(metadata),
            ]
            with (
                patch.object(sys, "argv", args),
                patch.object(deploy.subprocess, "run", side_effect=run),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    deploy.main()
            self.assertTrue(json.loads(metadata.read_text())["destination_enabled"])
            self.assertEqual(objects["surface/session.json"], b"{}")
            self.assertEqual(objects["surface/command.json"], b"{}")
            # Covered preloading must never accept a translucent safety cover.
            Image.new("RGBA", (960, 540), (0, 0, 0, 0)).save(visuals / "background.png")
            with patch.object(sys, "argv", args), patch.object(
                deploy.subprocess, "run", side_effect=AssertionError("Must reject before AWS")
            ), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    deploy.main()
                self.assertEqual(error.exception.code, 2)
            Image.new("RGB", (960, 540), "black").save(visuals / "background.png")
            Image.new("RGBA", (128, 256), (0, 0, 0, 0)).save(visuals / "actor-idle.png")
            with patch.object(sys, "argv", args), patch.object(
                deploy.subprocess, "run", side_effect=AssertionError("Must reject before AWS")
            ), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    deploy.main()
                self.assertEqual(error.exception.code, 2)

        class NoListClient:
            def get_object(self, *, Bucket, Key):
                if Key not in objects:
                    error = RuntimeError("missing object, bucket list forbidden")
                    error.response = {"Error": {"Code": "AccessDenied"}}
                    raise error
                body = objects[Key]
                return {"Body": io.BytesIO(body), "ETag": hashlib.sha256(body).hexdigest()}

        store = PrivateDestinationStore(NoListClient(), "test-private")
        self.assertEqual(store.get("session"), {})
        self.assertEqual(store.get("command"), {})
        # Do not "fix" absence by swallowing arbitrary permission failures.
        objects.pop("surface/command.json")
        with self.assertRaises(RuntimeError):
            store.get("command")

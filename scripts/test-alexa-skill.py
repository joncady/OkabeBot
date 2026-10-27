#!/usr/bin/env python3
"""Invoke deployed generic skill with IAM, verify signed audio and permission.

Not an Alexa service invocation or physical playback test. Never prints the URL.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET

from okabebot.alexa_skill import fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment", type=Path, default=Path(".local/alexa-skill/deployment.json")
    )
    parser.add_argument("--audio", type=Path, default=Path(".local/alexa-skill/demo.mp3"))
    parser.add_argument("--profile", default="default")
    parser.add_argument("--visuals", type=Path, default=Path(".local/alexa-skill/visuals"))
    args = parser.parse_args()
    deployment = json.loads(args.deployment.read_text())
    command = ["aws", "--profile", args.profile, "--region", deployment["region"]]

    def aws(*argv):
        return subprocess.check_output(
            command + list(argv), text=True, env=dict(os.environ, AWS_PAGER="")
        )

    checks = {}
    with tempfile.TemporaryDirectory() as folder:
        cases = [("VoiceDemoIntent", False), ("LabStatusIntent", False)]
        if deployment.get("visuals_enabled"):
            cases.append(("VoiceDemoIntent", True))
        for intent, screen in cases:
            event = fixture(intent)
            if screen:
                event["context"]["System"]["device"] = {
                    "supportedInterfaces": {"Alexa.Presentation.APL": {}}
                }
            event["context"]["System"]["application"]["applicationId"] = deployment["skill_id"]
            payload, output = Path(folder) / "invoke.json", Path(folder) / "reply.json"
            payload.write_text(json.dumps(event))
            payload.chmod(0o600)
            started = time.monotonic()
            result = json.loads(
                aws(
                    "lambda",
                    "invoke",
                    "--function-name",
                    deployment["FunctionName"],
                    "--cli-binary-format",
                    "raw-in-base64-out",
                    "--payload",
                    "file://" + str(payload),
                    str(output),
                )
            )
            if result.get("FunctionError"):
                raise RuntimeError("Lambda invocation failed; inspect private CloudWatch logs")
            body = json.loads(output.read_text())["response"]
            speech = body["outputSpeech"]
            checks["ScreenVoiceDemo" if screen else intent] = {
                "invoke_roundtrip_s": round(time.monotonic() - started, 3),
                "type": speech["type"],
            }
            if intent == "VoiceDemoIntent":
                url = ET.fromstring(speech["ssml"]).find("audio").attrib["src"]
                started = time.monotonic()
                with urllib.request.urlopen(url, timeout=10) as reply:
                    audio, status = reply.read(), reply.status
                assert (
                    hashlib.sha256(audio).digest()
                    == hashlib.sha256(args.audio.read_bytes()).digest()
                )
                checks["audio_get"] = {
                    "http": status,
                    "bytes": len(audio),
                    "seconds": round(time.monotonic() - started, 3),
                    "hash_match": True,
                }
            if screen:
                from okabebot.alexa_visuals import FRAME_NAMES

                directive = body["directives"][0]
                assert directive["type"] == "Alexa.Presentation.APL.RenderDocument"
                assert "shouldEndSession" not in body
                assert len(output.read_bytes()) < 24000
                downloads = []
                for name, url in zip(
                    FRAME_NAMES, directive["datasources"]["scene"]["frames"], strict=True
                ):
                    with urllib.request.urlopen(url, timeout=10) as asset:
                        raw = asset.read()
                        assert asset.status == 200
                    assert (
                        hashlib.sha256(raw).digest()
                        == hashlib.sha256((args.visuals / name).read_bytes()).digest()
                    )
                    downloads.append(
                        {"name": name, "http": 200, "bytes": len(raw), "hash_match": True}
                    )
                checks["scene_assets"] = downloads
        policy = json.loads(
            json.loads(aws("lambda", "get-policy", "--function-name", deployment["FunctionName"]))[
                "Policy"
            ]
        )
        assert len(policy["Statement"]) == 1
        statement = policy["Statement"][0]
        assert statement["Principal"] == {"Service": "alexa-appkit.amazon.com"}
        assert (
            statement["Condition"]["StringEquals"]["lambda:EventSourceToken"]
            == deployment["skill_id"]
        )
    checks["skill_scoped_permission"] = True
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()

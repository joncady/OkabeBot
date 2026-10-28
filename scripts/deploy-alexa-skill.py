#!/usr/bin/env python3
"""Deploy the development skill and opt-in adapters; the Mac stays private."""

import argparse
import base64
import zlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def source():
    protocol = (ROOT / "okabebot/alexa_skill.py").read_text()
    visuals = (ROOT / "okabebot/alexa_visuals.py").read_text()
    destination = (ROOT / "okabebot/alexa_destination.py").read_text()
    relay = (
        (ROOT / "okabebot/alexa_destination_relay.py")
        .read_text()
        .replace("from .alexa_destination import document, update", "")
    )
    conversation = (
        (ROOT / "okabebot/alexa_conversation.py")
        .read_text()
        .replace("from .alexa_skill import response, validate_envelope", "# Included above")
        .replace("from .alexa_destination_relay import DestinationRelay", "# Included above")
    )
    exchange = (
        (ROOT / "okabebot/alexa_conversation_relay.py")
        .read_text()
        .replace("from .alexa_conversation import digest", "# Included above")
    )
    source = (
        (ROOT / "infra/aws/alexa_skill.py")
        .read_text()
        .replace("from okabebot.alexa_skill import response, validate_envelope", "")
        .replace("from okabebot.alexa_visuals import attach_character, FRAME_NAMES", "")
        .replace("from okabebot.alexa_conversation import ConversationSkill", "# Included above")
        .replace("from okabebot.alexa_conversation_relay import aws_exchange", "# Included above")
        .replace(
            "from okabebot.alexa_destination_relay import DestinationRelay, PrivateDestinationStore",
            "# Included above",
        )
    )
    return "\n".join((protocol, visuals, destination, relay, conversation, exchange, source))


def template():
    value = json.loads((ROOT / "infra/aws/alexa-skill.json").read_text())
    packed = base64.b64encode(zlib.compress(source().encode(), level=9)).decode()
    value["Resources"]["Skill"]["Properties"]["Code"]["ZipFile"] = (
        "# Deterministic wrapper for reviewed source; avoids CFN's 51 KiB template limit.\n"
        "import base64, zlib\n"
        + "exec(compile(zlib.decompress(base64.b64decode("
        + repr(packed)
        + ")), 'little_lab_skill.py', 'exec'))\n"
    )
    return value


def bootstrap_destination(aws, bucket):
    """Seed both relay objects without overwriting an existing session/command.

    The Lambda intentionally lacks ListBucket, so an absent object would produce
    AccessDenied rather than NoSuchKey. Bootstrap uses the deployment principal.
    """
    with tempfile.TemporaryDirectory(prefix="okabebot-destination-") as folder:
        path = Path(folder) / "empty.json"
        path.write_text("{}")
        path.chmod(0o600)
        for key in ("surface/session.json", "surface/command.json"):
            for attempt in range(3):
                try:
                    aws(
                        "s3api",
                        "put-object",
                        "--bucket",
                        bucket,
                        "--key",
                        key,
                        "--body",
                        str(path),
                        "--if-none-match",
                        "*",
                        "--content-type",
                        "application/json",
                        "--cache-control",
                        "no-store",
                        "--server-side-encryption",
                        "AES256",
                    )
                    break
                except subprocess.CalledProcessError as exc:
                    if "PreconditionFailed" in (exc.stderr or ""):
                        break
                    if "ConditionalRequestConflict" not in (exc.stderr or "") or attempt == 2:
                        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-id", required=True)
    parser.add_argument(
        "--audio", type=Path, required=True, help="Generic, non-personal demo MP3 only"
    )
    parser.add_argument("--profile", default="default")
    parser.add_argument("--visuals", type=Path, help="Directory of generic generated scene frames")
    parser.add_argument(
        "--destination-visuals",
        type=Path,
        help="Experimental session destination layers and scene.json; disabled when omitted",
    )
    parser.add_argument(
        "--conversation-deployment",
        type=Path,
        help="Private conversation transport metadata; disabled when omitted",
    )
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--stack", default="okabebot-alexa-skill")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/alexa-skill/deployment.json")
    args = parser.parse_args()
    if not re.fullmatch(r"amzn1\.ask\.skill\.[a-zA-Z0-9-]+", args.skill_id):
        parser.error("Invalid skill ID")
    if args.audio.suffix != ".mp3" or not 100 < args.audio.stat().st_size < 2_000_000:
        parser.error("Use the small generic prototype MP3, never personal/reference audio")
    from okabebot.alexa_visuals import FRAME_NAMES

    if args.visuals:
        for name in FRAME_NAMES:
            if not 100 < (args.visuals / name).stat().st_size < 2_000_000:
                parser.error("Generate all four bounded scene frames before deploying")
    destination_scene = {"character": "okabe", "set": "pixel-lab"}
    destination_names = ["background.png", *["actor-" + name for name in FRAME_NAMES]]
    if args.destination_visuals:
        from okabebot.scene_sets import validate_selection

        from PIL import Image

        with Image.open(args.destination_visuals / "background.png") as background:
            dimensions = background.size
            if background.convert("RGBA").getchannel("A").getextrema() != (255, 255):
                parser.error("Destination background must be opaque to cover the preloaded actor")
        for name in destination_names[1:]:
            with Image.open(args.destination_visuals / name) as actor:
                if actor.size != dimensions:
                    parser.error("All destination actor frames must match background dimensions")
        destination_scene = json.loads((args.destination_visuals / "scene.json").read_text())
        validate_selection(destination_scene["character"], destination_scene["set"])
        for name in destination_names:
            if not 100 < (args.destination_visuals / name).stat().st_size < 2_000_000:
                parser.error("Generate bounded destination layers before enabling the relay")
    conversation = None
    if args.conversation_deployment:
        conversation = json.loads(args.conversation_deployment.read_text())
        required = (
            "ConversationQueueUrl",
            "ConversationQueueArn",
            "ConversationTableName",
            "ConversationAudioBucket",
            "paired_identity",
        )
        if any(not isinstance(conversation.get(k), str) or not conversation[k] for k in required):
            parser.error("Incomplete private conversation deployment metadata")
        if conversation.get("region") != args.region:
            parser.error("Conversation transport and skill must share a region")
        if not re.fullmatch(r"[a-f0-9]{64}", conversation["paired_identity"]):
            parser.error("Pair one approved Echo before enabling conversation")
    command = ["aws", "--profile", args.profile, "--region", args.region]

    def aws(*argv):
        return subprocess.run(
            command + list(argv),
            check=True,
            capture_output=True,
            text=True,
            env=dict(os.environ, AWS_PAGER=""),
        ).stdout

    try:
        aws("cloudformation", "describe-stacks", "--stack-name", args.stack)
        exists = True
    except subprocess.CalledProcessError as exc:
        if "does not exist" not in exc.stderr:
            raise
        exists = False
    request = {
        "StackName": args.stack,
        "TemplateBody": json.dumps(template()),
        "Capabilities": ["CAPABILITY_IAM"],
        "Parameters": [
            {"ParameterKey": "SkillId", "ParameterValue": args.skill_id},
            {
                "ParameterKey": "EnableVisuals",
                "ParameterValue": "true" if args.visuals else "false",
            },
        ],
        "Tags": [{"Key": "Project", "Value": "OkabeBot"}],
    }
    request["Parameters"].extend(
        [
            {
                "ParameterKey": "EnableDestination",
                "ParameterValue": "true" if args.destination_visuals else "false",
            },
            {
                "ParameterKey": "DestinationCharacter",
                "ParameterValue": destination_scene["character"],
            },
            {"ParameterKey": "DestinationSet", "ParameterValue": destination_scene["set"]},
        ]
    )
    request["Parameters"].append(
        {
            "ParameterKey": "EnableConversation",
            "ParameterValue": "true" if conversation else "false",
        }
    )
    for parameter, key in (
        ("ConversationQueueUrl", "ConversationQueueUrl"),
        ("ConversationQueueArn", "ConversationQueueArn"),
        ("ConversationTableName", "ConversationTableName"),
        ("ConversationAudioBucket", "ConversationAudioBucket"),
        ("ConversationIdentity", "paired_identity"),
    ):
        request["Parameters"].append(
            {"ParameterKey": parameter, "ParameterValue": conversation[key] if conversation else ""}
        )
    with tempfile.TemporaryDirectory(prefix="okabebot-alexa-") as folder:
        path = Path(folder) / "request.json"
        path.write_text(json.dumps(request))
        path.chmod(0o600)
        try:
            aws(
                "cloudformation",
                "update-stack" if exists else "create-stack",
                "--cli-input-json",
                "file://" + str(path),
            )
            print("Waiting for the skill stack…", flush=True)
            aws(
                "cloudformation",
                "wait",
                "stack-update-complete" if exists else "stack-create-complete",
                "--stack-name",
                args.stack,
            )
        except subprocess.CalledProcessError as exc:
            if "No updates are to be performed" not in exc.stderr:
                raise SystemExit(
                    "Deployment failed; inspect stack events. No private inputs printed."
                ) from None
    stack = json.loads(aws("cloudformation", "describe-stacks", "--stack-name", args.stack))[
        "Stacks"
    ][0]
    value = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
    # Keep the bucket private. Only Lambda issues short-lived HTTPS GET URLs.
    aws(
        "s3api",
        "put-object",
        "--bucket",
        value["AudioBucket"],
        "--key",
        "generic/demo.mp3",
        "--body",
        str(args.audio.resolve()),
        "--content-type",
        "audio/mpeg",
        "--cache-control",
        "private, max-age=300",
        "--server-side-encryption",
        "AES256",
    )
    if args.visuals:
        for name in FRAME_NAMES:
            aws(
                "s3api",
                "put-object",
                "--bucket",
                value["AudioBucket"],
                "--key",
                "generic/scene/" + name,
                "--body",
                str((args.visuals / name).resolve()),
                "--content-type",
                "image/png",
                "--cache-control",
                "private, max-age=300",
                "--server-side-encryption",
                "AES256",
            )
    if args.destination_visuals:
        bootstrap_destination(aws, value["AudioBucket"])
        for name in destination_names:
            aws(
                "s3api",
                "put-object",
                "--bucket",
                value["AudioBucket"],
                "--key",
                "surface/assets/" + name,
                "--body",
                str((args.destination_visuals / name).resolve()),
                "--content-type",
                "image/png",
                "--cache-control",
                "private, max-age=120",
                "--server-side-encryption",
                "AES256",
            )
    value.update(
        region=args.region,
        stack=args.stack,
        skill_id=args.skill_id,
        visuals_enabled=bool(args.visuals),
        conversation_enabled=bool(conversation),
        destination_enabled=bool(args.destination_visuals),
        destination_scene=destination_scene if args.destination_visuals else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + "\n")
    args.output.chmod(0o600)
    print("Skill endpoint and generic audio deployed. Private output file:", args.output)


if __name__ == "__main__":
    main()

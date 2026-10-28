"""Skill-scoped Lambda: generic voice demo only, no household tools or data.

Deployment prepends the shared protocol module for CloudFormation inline code.
An Alexa Skills Kit Lambda permission with EventSourceToken is REQUIRED. There
is no Function URL. Never log request envelopes or signed audio URLs.
"""

import os
import logging

from okabebot.alexa_skill import response, validate_envelope
from okabebot.alexa_visuals import attach_character, FRAME_NAMES


def handle(event, skill_id, audio_url, frames=None, destination=None):
    request = validate_envelope(event, skill_id)
    kind = request["type"]
    if kind == "Alexa.Presentation.APL.UserEvent":
        if destination is not None and request.get("arguments", [None])[:1] == ["destination-poll"]:
            return destination.poll(event)
        if (
            request.get("token") != "little-lab-character"
            or request.get("arguments") != ["little-lab-mounted"]
            or request.get("source", {}).get("handler") != "Mount"
        ):
            raise ValueError("Unknown visual diagnostic event")
        logging.getLogger(__name__).warning("little_lab_visual document=mounted")
        # Mount is diagnostic only: it can occur for invisible components and
        # does not prove artwork loaded or transfer character ownership.
        return {"version": "1.0", "response": {}}
    if kind == "SessionEndedRequest":
        if destination is not None:
            destination.closed(event)
        logging.getLogger(__name__).warning("little_lab_visual session=ended")
        return {"version": "1.0", "response": {}}
    if kind == "LaunchRequest":
        result = response("", audio_url=audio_url(), end=False)
        result["response"]["reprompt"] = {
            "outputSpeech": {"type": "PlainText", "text": "Try asking for a voice demo."}
        }
        return attach_character(result, event, frames) if frames else result
    if kind != "IntentRequest":
        raise ValueError("Unsupported request type")
    intent = request["intent"]["name"]
    known = {
        "VoiceDemoIntent",
        "VisitIntent",
        "LabStatusIntent",
        "LabLocationsIntent",
        "AMAZON.StopIntent",
        "AMAZON.CancelIntent",
        "AMAZON.HelpIntent",
        "AMAZON.FallbackIntent",
    }
    logging.getLogger(__name__).warning(
        "little_lab_request intent=%s", intent if intent in known else "Other"
    )
    if intent == "VisitIntent":
        if destination is None:
            return response(
                "The screen destination is not enabled yet. You can ask for a voice demo."
            )
        if "Alexa.Presentation.APL" not in event.get("context", {}).get("System", {}).get(
            "device", {}
        ).get("supportedInterfaces", {}):
            return response(
                "Please open Little Lab on a screen-capable Echo to visit this destination."
            )
        return destination.launch(event)
    if intent == "VoiceDemoIntent":
        result = response("", audio_url=audio_url())
        return attach_character(result, event, frames) if frames else result
    if intent in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
        return response("See you in the lab.")
    if intent in ("LabStatusIntent", "LabLocationsIntent"):
        return response(
            "The Alexa skill is connected. Local lab tools are not linked to this skill yet."
        )
    return response("Ask Little Lab for a voice demo.")


def handler(event, context):
    import boto3
    from botocore.config import Config

    client = boto3.client("s3", config=Config(signature_version="s3v4"))

    def audio_url():
        # Only this fixed, generic asset can be fetched. Never accept an object
        # key or URL from request slots. The bucket itself remains private.
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": os.environ["AUDIO_BUCKET"], "Key": "generic/demo.mp3"},
            ExpiresIn=300,
        )

    def frames():
        return [
            client.generate_presigned_url(
                "get_object",
                Params={"Bucket": os.environ["AUDIO_BUCKET"], "Key": "generic/scene/" + name},
                ExpiresIn=300,
            )
            for name in FRAME_NAMES
        ]

    destination = None
    if os.environ.get("DESTINATION_ENABLED") == "true":
        from okabebot.alexa_destination_relay import DestinationRelay, PrivateDestinationStore

        def destination_assets():
            def sign(name):
                return client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": os.environ["AUDIO_BUCKET"], "Key": "surface/assets/" + name},
                    ExpiresIn=120,
                )

            return {
                "background": sign("background.png"),
                "frames": [sign("actor-" + name) for name in FRAME_NAMES],
                "character": os.environ["DESTINATION_CHARACTER"],
                "set": os.environ["DESTINATION_SET"],
            }

        destination = DestinationRelay(
            PrivateDestinationStore(client, os.environ["AUDIO_BUCKET"]), destination_assets
        )
    return handle(
        event,
        os.environ["SKILL_ID"],
        audio_url,
        frames if os.environ.get("VISUALS_ENABLED") == "true" else None,
        destination,
    )

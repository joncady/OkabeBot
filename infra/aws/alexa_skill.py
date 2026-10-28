"""Skill-scoped Lambda: generic voice demo only, no household tools or data.

Deployment prepends the shared protocol module for CloudFormation inline code.
An Alexa Skills Kit Lambda permission with EventSourceToken is REQUIRED. There
is no Function URL. Never log request envelopes or signed audio URLs.
"""

import os
import logging

from okabebot.alexa_skill import response, validate_envelope
from okabebot.alexa_visuals import attach_character, FRAME_NAMES


def handle(event, skill_id, audio_url, frames=None):
    request = validate_envelope(event, skill_id)
    kind = request["type"]
    if kind == "Alexa.Presentation.APL.UserEvent":
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

    return handle(
        event,
        os.environ["SKILL_ID"],
        audio_url,
        frames if os.environ.get("VISUALS_ENABLED") == "true" else None,
    )

"""Skill-scoped Lambda: generic voice demo only, no household tools or data.

Deployment prepends the shared protocol module for CloudFormation inline code.
An Alexa Skills Kit Lambda permission with EventSourceToken is REQUIRED. There
is no Function URL. Never log request envelopes or signed audio URLs.
"""

import os
import logging
import time

from okabebot.alexa_skill import response, validate_envelope
from okabebot.alexa_visuals import attach_character, FRAME_NAMES


def handle(event, skill_id, audio_url, frames=None, destination=None, conversation=None):
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
        if conversation is not None:
            try:
                conversation.cancel(event)
            except Exception:
                logging.getLogger(__name__).warning("little_lab_conversation cleanup_failed")
        if destination is not None:
            destination.closed(event)
        logging.getLogger(__name__).warning("little_lab_visual session=ended")
        return {"version": "1.0", "response": {}}
    if kind == "LaunchRequest":
        if destination is not None and "Alexa.Presentation.APL" in event.get("context", {}).get(
            "System", {}
        ).get("device", {}).get("supportedInterfaces", {}):
            return destination.launch(event)
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
        "TalkIntent",
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
    if intent == "TalkIntent":
        if conversation is None:
            return response("Conversation is not connected yet. You can ask for a voice demo.")
        try:
            return conversation.handle(event)
        except PermissionError:
            return response("This Echo is not paired for companion conversations.")
        except ValueError:
            return response("Say tell me, followed by a short question.", end=False)
        except Exception:
            logging.getLogger(__name__).warning("little_lab_conversation unavailable")
            return response("The companion is unavailable. Please try again shortly.", end=False)
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
        if conversation is not None:
            try:
                conversation.cancel(event)
            except Exception:
                logging.getLogger(__name__).warning("little_lab_conversation cleanup_failed")
        if destination is not None:
            destination.closed(event, explicit=True)
        return response("See you in the lab.")
    if intent in ("LabStatusIntent", "LabLocationsIntent"):
        return response(
            "The Alexa skill is connected. Local lab tools are not linked to this skill yet."
        )
    return response("Ask Little Lab for a voice demo.")


def handler(event, context):
    started = time.monotonic()
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        config=Config(
            signature_version="s3v4",
            connect_timeout=0.3,
            read_timeout=0.3,
            retries={"total_max_attempts": 1},
        ),
    )

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
    conversation = None
    if os.environ.get("CONVERSATION_ENABLED") == "true":
        from okabebot.alexa_conversation import ConversationSkill
        from okabebot.alexa_conversation_relay import aws_exchange, bounded_call

        def sign_reply(key):
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": os.environ["CONVERSATION_AUDIO_BUCKET"], "Key": key},
                ExpiresIn=120,
            )

        def visual_reply(event, character, duration):
            if destination is None:
                return None
            try:
                return bounded_call(
                    destination.speech, time.time() + 0.2, time.time, event, character, duration
                )
            except Exception:
                logging.getLogger(__name__).warning("little_lab_conversation visual_unavailable")
                return None

        remaining = (
            context.get_remaining_time_in_millis() / 1000
            if context is not None
            else 7 - (time.monotonic() - started)
        )
        budget = max(0, min(6, remaining - 0.65))
        logging.getLogger(__name__).warning(
            "little_lab_conversation setup_s=%.3f budget_s=%.3f",
            time.monotonic() - started,
            budget,
        )
        conversation = ConversationSkill(
            os.environ["SKILL_ID"],
            os.environ["CONVERSATION_IDENTITY"],
            aws_exchange(
                boto3.Session(), os.environ["CONVERSATION_TABLE"], os.environ["CONVERSATION_QUEUE"]
            ),
            sign_reply,
            visual=visual_reply if destination is not None else None,
            budget=budget,
        )
    return handle(
        event,
        os.environ["SKILL_ID"],
        audio_url,
        frames if os.environ.get("VISUALS_ENABLED") == "true" else None,
        destination,
        conversation,
    )

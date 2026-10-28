"""Bounded conversation protocol; no tools, audio upload or network listener.

The cloud adapter authenticates/pairs an Echo before passing a request to an
injected durable transport. The Mac worker owns generation and audio eligibility.
"""

import hashlib
import re
import time

from .alexa_skill import response, validate_envelope
from .alexa_destination_relay import DestinationRelay


PROMPT_LIMIT = 600
FALLBACK = "The companion did not finish in time. Please try a shorter question."


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def question(event, skill_id, paired_identity, *, now=time.time):
    request = validate_envelope(event, skill_id)
    if not re.fullmatch(r"[a-f0-9]{64}", paired_identity or ""):
        raise PermissionError("Conversation pairing is required")
    identity = DestinationRelay.identity(event)
    if identity != paired_identity:
        raise PermissionError("This Echo is not paired for conversation")
    if (
        request.get("type") != "IntentRequest"
        or request.get("intent", {}).get("name") != "TalkIntent"
    ):
        raise ValueError("Expected a conversation intent")
    value = request["intent"].get("slots", {}).get("Query", {}).get("value")
    if not isinstance(value, str) or not value.strip() or len(value) > PROMPT_LIMIT:
        raise ValueError("Use a short spoken question")
    value = " ".join(value.split())
    session = event.get("session", {}).get("sessionId")
    # No raw account, device, session or Alexa request identifiers cross the relay.
    key = digest(identity + "\0" + request["requestId"])
    return {
        "id": key,
        "identity": identity,
        "session": digest(identity + "\0" + (session or request["requestId"])),
        "text": value,
        "body_hash": digest(value),
        "deadline": now() + 6,
    }


def reply(result, request, sign_audio):
    """Only worker-approved generic audio, with a fixed application-owned key."""
    if result.get("id") != request["id"] or result.get("body_hash") != request["body_hash"]:
        raise ValueError("Reply does not match its request")
    text = result.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 600:
        raise ValueError("Invalid conversation reply")
    audio_url = None
    if result.get("audio_safe") is True and result.get("audio_ready") is True:
        # Neither the model nor incoming slots supply object keys or URLs.
        audio_url = sign_audio("conversation/audio/" + request["id"] + ".mp3")
    value = response(text, audio_url=audio_url, end=False)
    value["response"]["reprompt"] = {
        "outputSpeech": {"type": "PlainText", "text": "Say tell me, followed by your question."}
    }
    return value


class ConversationSkill:
    """Injected durable exchange; bounded wait and truthful timeout fallback.

    exchange.open must atomically create-or-read a request, reject a different
    body for an existing ID, and preserve the original deadline. A consumer must
    atomically claim it before generation; an uncertain turn is never replayed.
    """

    def __init__(self, skill_id, paired_identity, exchange, sign_audio, *, clock=time.monotonic):
        self.skill_id, self.paired_identity = skill_id, paired_identity
        self.exchange, self.sign_audio, self.clock = exchange, sign_audio, clock

    def handle(self, event):
        end = self.clock() + 6.2
        request = question(event, self.skill_id, self.paired_identity)
        try:
            record = self.exchange.open(request)
            if record["body_hash"] != request["body_hash"]:
                raise ValueError("Request ID was reused with different content")
            request["deadline"] = record["deadline"]
            if request["deadline"] <= time.time():
                return response(FALLBACK, end=False)
            # Transport owns bounded blocking, including its individual network calls.
            result = self.exchange.wait(request, end)
            if result is None or self.clock() >= end or request["deadline"] <= time.time():
                return response(FALLBACK, end=False)
            return reply(result, request, self.sign_audio)
        except TimeoutError:
            return response(FALLBACK, end=False)


def audio_eligible(question_text, answer):
    """Conservative second gate, not a guarantee of semantic privacy detection.

    Model eligibility alone is insufficient. No private tools/context are ever
    attached; suspicious input/output stays native text instead of custom audio.
    """
    if not isinstance(answer, dict) or set(answer) != {"text", "audio_safe"}:
        raise ValueError("Invalid model conversation format")
    text = answer["text"]
    if not isinstance(text, str) or not text.strip() or len(text) > 200:
        raise ValueError("Use a short generated answer")
    if type(answer["audio_safe"]) is not bool:
        raise ValueError("Explicit audio eligibility is required")
    combined = question_text + " " + text
    suspect = re.search(
        r"https?://|[\w.+-]+@[\w.-]+|(?:\d[\s().+-]*){7,}|"
        r"\b(?:password|passcode|secret|address|calendar|inbox|bank|medical|"
        r"my phone|my name|my family|my home|my account|my messages)\b",
        combined,
        re.IGNORECASE,
    )
    return answer["audio_safe"] and not suspect

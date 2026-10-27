"""Offline custom-skill protocol prototype. This is NOT an HTTP ingress.

A real endpoint must use ASK signature/timestamp verification (or an Alexa-only
Lambda trigger) before calling this code. Never expose this harness as a server.
"""

import datetime as dt
import time
from html import escape
from urllib.parse import urlsplit


DEMO_TEXT = "The little lab is connected. The experiments can wait. Hello there."


def validate_envelope(event, app_id, user_id=None):
    system = event["context"]["System"]
    if system["application"]["applicationId"] != app_id:
        raise PermissionError("Skill not allowed")
    session_app = event.get("session", {}).get("application", {}).get("applicationId")
    if session_app and session_app != app_id:
        raise PermissionError("Session skill mismatch")
    if user_id is not None and system["user"]["userId"] != user_id:
        raise PermissionError("Account not allowed")
    request = event["request"]
    stamp = dt.datetime.fromisoformat(request["timestamp"].replace("Z", "+00:00"))
    if stamp.tzinfo is None or not -5 <= time.time() - stamp.timestamp() <= 150:
        raise ValueError("Stale skill request")
    key = request["requestId"]
    if not isinstance(key, str) or not 1 <= len(key) <= 300:
        raise ValueError("Invalid request ID")
    return request


def response(text, *, audio_url=None, end=True):
    if audio_url:
        url = urlsplit(audio_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("Audio requires a trusted public HTTPS asset URL")
        speech = {
            "type": "SSML",
            "ssml": '<speak><audio src="%s"/></speak>' % escape(audio_url, quote=True),
        }
    else:
        speech = {"type": "PlainText", "text": text[:1200]}
    return {"version": "1.0", "response": {"outputSpeech": speech, "shouldEndSession": end}}


class Prototype:
    """Injected read-only tools, bounded intents, and deterministic protocol replies.

    No arbitrary utterance-to-tool execution, no recording, no automatic playback,
    and no public asset upload. The response cache is process-local, not a durable
    production replay ledger. All prototype tools are read-only.
    """

    def __init__(self, app_id, user_id, tools, *, audio_url=None):
        self.app_id, self.user_id = app_id, user_id
        self.tools, self.audio_url = tools, audio_url
        self.responses = {}

    def handle(self, event):
        request = validate_envelope(event, self.app_id, self.user_id)
        key = request["requestId"]
        if key in self.responses:
            return self.responses[key]
        kind = request["type"]
        if kind == "SessionEndedRequest":
            result = {"version": "1.0", "response": {}}
        elif kind == "LaunchRequest":
            result = response(
                "The lab is ready. Ask for status, locations, or a voice demo.", end=False
            )
            result["response"]["reprompt"] = {
                "outputSpeech": {"type": "PlainText", "text": "Try asking for lab status."}
            }
        elif kind == "IntentRequest":
            name = request["intent"]["name"]
            if name == "LabStatusIntent":
                # Use the shared tool, but do not serialize private health details
                # into an uploaded Qwen asset. Alexa speaks this result normally.
                self.tools["get_device_health"]()
                result = response(
                    "The controller is responding. Device health is available in the dashboard."
                )
            elif name == "LabLocationsIntent":
                data = self.tools["get_companion_locations"]()
                names = [p["name"] for p in data["locations"] if p.get("approved", True)]
                result = response(
                    "Registered screens: " + ", ".join(names[:12])
                    if names
                    else "No screens are registered."
                )
            elif name == "VoiceDemoIntent":
                result = response(DEMO_TEXT, audio_url=self.audio_url)
            elif name in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
                result = response("See you in the lab.")
            else:
                result = response("Try lab status, available screens, or a voice demo.")
        else:
            raise ValueError("Unsupported request type")
        if len(self.responses) >= 128:
            self.responses.pop(next(iter(self.responses)))
        self.responses[key] = result
        return result


def fixture(intent="LabStatusIntent"):
    """Explicit synthetic credentials; never a captured household request."""
    return {
        "version": "1.0",
        "context": {
            "System": {
                "application": {"applicationId": "local-prototype"},
                "user": {"userId": "local-test-user"},
            }
        },
        "request": {
            "type": "IntentRequest",
            "requestId": "prototype-" + str(time.time_ns()),
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "intent": {"name": intent, "slots": {}},
        },
    }

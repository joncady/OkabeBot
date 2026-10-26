"""Explicit named Echo speech through a private Home Assistant webhook."""

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from .spotify import env_value


def speakers():
    try:
        values = json.loads(env_value("OKABEBOT_ECHO_SPEAKERS") or "{}")
        if not isinstance(values, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) or not v.startswith("notify.")
            for k, v in values.items()
        ):
            raise ValueError()
        return values
    except ValueError:
        raise ValueError(
            "Configure OKABEBOT_ECHO_SPEAKERS privately as a name-to-notify-entity JSON object"
        ) from None


def speak(speaker, text, dry_run=False):
    from html import escape

    if type(dry_run) is not bool:
        raise ValueError("dry_run must be boolean")
    targets = speakers()
    if speaker not in targets:
        raise ValueError("Choose a configured Echo name; use list_echo_speakers first")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
        raise ValueError("Speech must contain 1–500 characters")
    url = env_value("OKABEBOT_ECHO_WEBHOOK")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.netloc
        or not parsed.path.startswith("/api/webhook/")
    ):
        raise ValueError("Configure the private Home Assistant speech webhook first")
    if dry_run:
        return {"speaker": speaker, "configured": True, "dry_run": True}
    payload = json.dumps(
        {
            "speaker": targets[speaker],
            "message": '<speak><prosody volume="soft">' + escape(text) + "</prosody></speak>",
        }
    ).encode()
    try:
        with urlopen(
            Request(url, data=payload, headers={"Content-Type": "application/json"}), timeout=10
        ) as response:
            response.read(1024)
    except Exception:
        raise ValueError(
            "Echo request failed or outcome unknown; do not retry automatically"
        ) from None
    return {"speaker": speaker, "accepted": True, "playback_confirmed": False}

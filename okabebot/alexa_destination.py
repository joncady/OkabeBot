"""Session-scoped APL destination renderer. Cloud/local relay is not enabled yet.

No tools or device discovery here. A trusted adapter supplies signed artwork and
only sends enter after the source's rendered-away acknowledgement. Client-side
clock expiry hides the actor independently of a future relay's availability.
"""

import re
from urllib.parse import urlsplit


PHASES = {"waiting", "entering", "present", "leaving", "hidden"}


def credential(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Use a fresh 256-bit session token")
    return value


def signed_image(value):
    if not isinstance(value, str):
        raise ValueError("Expected a trusted HTTPS image URL")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Expected a trusted HTTPS image URL")
    return value


def set_value(name, value):
    return {"type": "SetValue", "componentId": "destination", "property": name, "value": value}


def document(token, background, frames):
    """Create an initially empty room; no implied arrival or microphone opening.

    Polling runs in a bounded normal-mode mount sequencer. Clock/expiry runs in
    fast-mode ticks and must never contain SendEvent. Asset readiness is reported
    separately from mount. This renderer is experimental until tested on hardware.
    """
    credential(token)
    if not isinstance(frames, list) or len(frames) != 4:
        raise ValueError("Four transparent actor frames required")
    urls = [signed_image(background), *map(signed_image, frames)]
    root = {
        "type": "Container",
        "id": "destination",
        "width": "100vw",
        "height": "100vh",
        "bind": [
            {"name": k, "value": v}
            for k, v in {
                "phase": "waiting",
                "generation": "",
                "painted": "hidden",
                "leaseUntil": 0,
                "clock": 0,
                "sequence": 0,
                "incoming": {},
                "appliedAt": 0,
                "closed": False,
                "backgroundReady": False,
                "actorReady": False,
                "frame": 0,
            }.items()
        ],
        "items": [
            {
                "type": "Image",
                "width": "100%",
                "height": "100%",
                "scale": "best-fit",
                "source": "${payload.scene.background}",
                "onLoad": [set_value("backgroundReady", True)],
            },
            {
                "type": "Image",
                "id": "actor",
                "position": "absolute",
                "width": "100%",
                "height": "100%",
                "scale": "best-fit",
                "source": "${payload.scene.frames[frame]}",
                "opacity": "${!closed && actorReady && clock < 60000 && clock < leaseUntil && (phase == 'entering' || phase == 'present' || phase == 'leaving') ? 1 : 0}",
                "onLoad": [set_value("actorReady", True)],
            },
        ],
        "handleTick": [
            {
                "minimumDelay": 100,
                "commands": [
                    set_value("clock", "${elapsedTime}"),
                    {
                        "type": "Sequential",
                        "when": "${!closed && elapsedTime < 60000 && incoming.sequence > sequence && (incoming.expiresAt > elapsedTime || incoming.phase == 'hidden' || incoming.phase == 'waiting')}",
                        "commands": [
                            set_value("sequence", "${incoming.sequence}"),
                            set_value("generation", "${incoming.generation}"),
                            set_value(
                                "phase",
                                "${incoming.phase == 'leaving' ? 'hidden' : incoming.phase}",
                            ),
                            set_value("leaseUntil", "${incoming.expiresAt}"),
                            set_value("appliedAt", "${elapsedTime}"),
                            set_value("painted", "pending"),
                        ],
                    },
                    {
                        **set_value("painted", "entered"),
                        "when": "${!closed && backgroundReady && actorReady && (phase == 'entering' || phase == 'present') && elapsedTime < leaseUntil && elapsedTime >= appliedAt + 100}",
                    },
                    {
                        "type": "Sequential",
                        "when": "${((phase == 'entering' || phase == 'present') && elapsedTime >= leaseUntil) || (elapsedTime >= 60000 && phase != 'hidden')}",
                        "commands": [
                            set_value("phase", "hidden"),
                            set_value("leaseUntil", 0),
                            set_value("appliedAt", "${elapsedTime}"),
                            set_value("painted", "pending"),
                        ],
                    },
                    {
                        **set_value("painted", "departed"),
                        "when": "${phase == 'hidden' && elapsedTime >= appliedAt + 100}",
                    },
                    {**set_value("closed", True), "when": "${elapsedTime >= 60000}"},
                    set_value("frame", "${elapsedTime % 4000 >= 3860 ? 3 : 0}"),
                ],
            }
        ],
        "onMount": [
            {
                "type": "Sequential",
                "sequencer": "destination-poll",
                "repeatCount": 59,
                "commands": [
                    {
                        "type": "SendEvent",
                        "arguments": [
                            "destination-poll",
                            token,
                            "${generation}",
                            "${painted}",
                            "${backgroundReady && actorReady}",
                            "${elapsedTime}",
                        ],
                    },
                    {"type": "Idle", "delay": 1000},
                ],
                "finally": [set_value("phase", "hidden"), set_value("leaseUntil", 0)],
            }
        ],
    }
    return {
        "version": "1.0",
        "response": {
            "directives": [
                {
                    "type": "Alexa.Presentation.APL.RenderDocument",
                    "token": token,
                    "document": {
                        "type": "APL",
                        "version": "1.8",
                        "settings": {"idleTimeout": 65000},
                        "mainTemplate": {"parameters": ["payload"], "items": [root]},
                    },
                    "datasources": {"scene": {"background": urls[0], "frames": urls[1:]}},
                }
            ]
        },
    }


def update(token, phase, generation, *, sequence, receiver_elapsed_ms, lease_ms=4000):
    """Send a mailbox value; root component ticks validate and apply it.

    The lease is anchored to the originating poll's receiver clock. Delayed replies
    cannot create a fresh lease on arrival. Root-bound variables are deliberately
    not read in ExecuteCommands' document-level data-binding context.
    """
    credential(token)
    if (
        phase not in PHASES
        or not isinstance(generation, str)
        or not re.fullmatch(r"[a-f0-9]{32}", generation)
    ):
        raise ValueError("Invalid destination transition")
    if type(sequence) is not int or not 1 <= sequence <= 1000000:
        raise ValueError("Use a monotonically increasing command sequence")
    if type(receiver_elapsed_ms) is not int or not 0 <= receiver_elapsed_ms < 60000:
        raise ValueError("Expected the originating poll's receiver elapsed time")
    if type(lease_ms) is not int or not 1000 <= lease_ms <= 4000:
        raise ValueError("Visibility lease must be 1–4 seconds")
    visible = phase in {"entering", "present", "leaving"}
    value = {
        "sequence": sequence,
        "phase": phase,
        "generation": generation,
        "expiresAt": min(60000, receiver_elapsed_ms + lease_ms) if visible else 0,
    }
    return {
        "version": "1.0",
        "response": {
            "directives": [
                {
                    "type": "Alexa.Presentation.APL.ExecuteCommands",
                    "token": token,
                    "commands": [set_value("incoming", value)],
                }
            ]
        },
    }

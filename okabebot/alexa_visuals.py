"""Small APL adapter over pre-rendered shared pixel artwork, not a browser port."""

FRAME_NAMES = ("idle.png", "talk-a.png", "talk-b.png", "blink.png")


def attach_character(result, event, frames):
    """Attach only on APL devices; leave audio-only Echo responses unchanged.

    Frames are supplied by a trusted fixed-asset signer, never from Alexa slots.
    Speaking is a bounded decorative loop, not audio-envelope lip sync.
    """
    supported = (
        event.get("context", {}).get("System", {}).get("device", {}).get("supportedInterfaces", {})
    )
    if "Alexa.Presentation.APL" not in supported:
        return result
    urls = frames()
    if len(urls) != 4 or not all(isinstance(u, str) and u.startswith("https://") for u in urls):
        raise ValueError("Four trusted HTTPS character frames are required")

    def pose(number):
        return {"type": "SetValue", "componentId": "lab", "property": "frame", "value": number}

    document = {
        "type": "APL",
        "version": "1.8",
        "settings": {"idleTimeout": 120000},
        "mainTemplate": {
            "parameters": ["payload"],
            "items": [
                {
                    "type": "Container",
                    "id": "lab",
                    "width": "100vw",
                    "height": "100vh",
                    "bind": [{"name": "frame", "value": 0}],
                    "items": [
                        {
                            "type": "Frame",
                            "width": "100%",
                            "height": "100%",
                            "backgroundColor": "#101b27",
                            "item": {
                                "type": "Image",
                                "width": "100%",
                                "height": "100%",
                                "scale": "best-fit",
                                "source": "${payload.scene.frames[frame]}",
                            },
                        }
                    ],
                    "onMount": [
                        {
                            "type": "Sequential",
                            "sequencer": "character",
                            "commands": [
                                {
                                    "type": "Sequential",
                                    "repeatCount": 7,
                                    "commands": [
                                        pose(1),
                                        {"type": "Idle", "delay": 140},
                                        pose(2),
                                        {"type": "Idle", "delay": 140},
                                        pose(0),
                                        {"type": "Idle", "delay": 180},
                                    ],
                                },
                                {
                                    "type": "Sequential",
                                    "repeatCount": 23,
                                    "commands": [
                                        {"type": "Idle", "delay": 4000},
                                        pose(3),
                                        {"type": "Idle", "delay": 140},
                                        pose(0),
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        },
    }
    result["response"]["directives"] = [
        {
            "type": "Alexa.Presentation.APL.RenderDocument",
            "token": "little-lab-character",
            "document": document,
            "datasources": {"scene": {"frames": urls}},
        }
    ]
    # A screen session without immediately opening the microphone. Alexa owns
    # actual timeout/persistence; the idleTimeout above is only a recommendation.
    result["response"].pop("shouldEndSession", None)
    result["response"].pop("reprompt", None)
    return result

"""Character-led welcome prose; inbox facts never enter a model prompt."""

import re

from .arrival import QUIPS
from .profiles import current_character

EXAMPLES = {
    "kurisu": [
        "Welcome back. I suppose I can admit it's nice to have you here.",
        "There you are. I was almost getting used to the peace and quiet.",
    ],
    "okabe": [
        "You've returned! A most welcome development, if you ask me.",
        "Ah, there you are. Good. I was beginning to get sentimental.",
    ],
    "sonic": [
        "Hey, welcome back. Good to have you around.",
        "There you are. Glad you're back, pal.",
    ],
    "pip": [
        "Welcome home. It's nice having you here.",
        "Oh, you're back. That makes me happy.",
    ],
}


def validate_intro(text):
    if not isinstance(text, str):
        raise ValueError("Welcome must be text")
    text = " ".join(text.split()).strip('"')
    if not 8 <= len(text) <= 180 or any(c in text for c in "<>{}[]`"):
        raise ValueError("Welcome must be short plain speech")
    if re.search(r"\b(tool_call|arguments|function|request_id)\b", text, re.I):
        raise ValueError("Welcome cannot contain a tool call")
    if re.search(
        r"\b(saw|heard|smell\w*|scent|watched|monitored|recorded|detected|noticed|sensors?)\b",
        text,
        re.I,
    ):
        raise ValueError("Welcome cannot claim sensory observations")
    return text


def message(item, composer=None):
    """Generate only an intro; append the already-grounded recap verbatim.

    Old fixed intros remain reference examples and a generation-failure fallback.
    A fresh character selection applies at delivery time, rather than queue time.
    """
    character = current_character()
    reference = QUIPS.get(character.get("style"), QUIPS["pip"])
    recap = item["body"]
    for old_intro in QUIPS.values():
        if recap.startswith(old_intro):
            recap = recap[len(old_intro) :].strip()
            break
    generated = False
    intro = reference
    if composer:
        try:
            intro = validate_intro(composer(character, reference))
            generated = True
        except InterruptedError:
            raise
        except Exception:
            # No retry or second agent/model turn for an ambient greeting.
            pass
    return (intro + " " + recap).strip()[:550], generated

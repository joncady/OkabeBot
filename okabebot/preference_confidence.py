"""Conservative evidence score, not a calibrated probability or model self-rating."""

import re

DEFAULTS = {"auto_accept": True, "threshold": 0.9}
KEY = "conversation.memory_policy"


def confidence(text, memory):
    value = text.casefold().replace("’", "'")
    if (
        re.search(
            r"\b(but|however|not|never|don't|maybe|might|perhaps|sometimes|tonight|today|for now|not sure|don't remember|do not remember|hypothetically|if i|used to)\b",
            value,
        )
        or "?" in value
    ):
        return 0.4
    if re.search(
        r"\b(health|diagnos\w*|medication|depress\w*|anxiety|allerg\w*|weight|disease|diabet\w*)\b",
        value,
    ):
        return 0.4
    # A quoted phrase or someone else's taste is insufficient evidence of ownership.
    if '"' in value or re.search(r"\b(he|she|they|friend|wife|husband|says|said)\b", value):
        return 0.5
    explicit = re.search(
        r"\bi\s+(?:(?:usually|generally|really|always)\s+)?(?:like|love|enjoy|prefer|dislike|hate|avoid)\b",
        value,
    )
    grounded = all(v.casefold() in value for v in memory["values"])
    if explicit and grounded:
        return 0.95
    return 0.65

"""Shared bounded local tool protocol; source text never authorizes actions."""

from .prompts import prompt

import json
import re

MAX_CALLS = 3
MAX_SECONDS = 60

# Versioned operational policy lives apart from character/style references.

ROUTING = prompt("routing")

CONTINUATION = prompt("continuation")


def conversational(output):
    try:
        return json.loads(output) == {"conversation": True}
    except (ValueError, TypeError):
        return False


def dangling_promise(text):
    return bool(
        re.search(
            r"\b(let me (?:check|look|fetch|find)|I(?:'ll| will| am going to) (?:check|look|fetch|find)|checking (?:that|now))\b",
            text.replace("’", "'"),
            re.I,
        )
    )


def evidence(name, args, actual, reference):
    from .tool_reply import facts

    # Provider IDs/credentials are excluded by the shared human-facing projection.
    value = facts(name, actual, reference)
    if name == "get_context_feed":
        value["source"] = args.get("source")
        value["next_offset"] = actual.get("next_offset") if isinstance(actual, dict) else None
    return value

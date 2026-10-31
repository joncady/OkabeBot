"""Versionable conversation policy; dynamic source data is appended separately."""

from .prompts import prompt

import json


CONVERSATION = prompt("conversation")

MEMORY = prompt("memory")


PREFERENCE = CONVERSATION + " " + MEMORY + " "


def dispatcher_prompt(policy):
    """Operational routing has no character identity or theatrical instructions."""
    return prompt("dispatcher", policy=policy)


def response_prompt(policy, persona):
    """Keep optional character style subordinate to operational/factual contracts."""
    return prompt("response-style", policy=policy, persona=json.dumps(str(persona)[:2000]))

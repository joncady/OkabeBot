"""Discover directory-owned characters; Python 3.7 satellite compatible."""

from functools import lru_cache
from importlib import import_module
import pkgutil
from .base import Character


@lru_cache(maxsize=1)
def registry():
    values = []
    for info in pkgutil.iter_modules(__path__):
        if info.ispkg and not info.name.startswith("_"):
            value = import_module(__name__ + "." + info.name).CHARACTER
            if not isinstance(value, Character):
                raise TypeError("Character directories must implement Character")
            values.append(value)
    return {
        c.identity: c
        for c in sorted(values, key=lambda c: (c.definition.get("order", 100), c.identity))
    }


def get(identity):
    try:
        return registry()[identity]
    except (KeyError, TypeError):
        raise ValueError("Unknown character")


def motion_catalog():
    definitions = {key: value.motion() for key, value in registry().items()}
    clips = {}
    for value in definitions.values():
        clips.update(value["clips"])
    return dict(
        version=2,
        idle_cycle_seconds=32,
        idle_start_seconds=20,
        characters={k: v["idle"] for k, v in definitions.items()},
        work_stages=dict(
            researching="read",
            comparing="read",
            drafting="write",
            awaiting_review="review",
            blocked="review",
        ),
        clips=clips,
        definitions=definitions,
    )

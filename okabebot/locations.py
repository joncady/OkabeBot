"""Named destinations shared by configuration, voice tools and surface adapters."""

import copy
import re

DEFAULT_LOCATIONS = [
    {
        "id": "companion",
        "name": "Companion display",
        "aliases": ["Pi", "small screen"],
        "adapter": "pi",
    },
    {
        "id": "living-room",
        "name": "Living room TV",
        "aliases": ["TV", "television", "big screen"],
        "adapter": "cast",
    },
]
MOVE_VERB = r"\b(move|come|go|return|send|head|travel)\b"


def normalized(value):
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def validate(settings):
    values = settings["locations"]
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("Configure one Pi destination and one Cast destination")
    ids, names, adapters = set(), {}, []
    for item in values:
        if not isinstance(item, dict) or set(item) != {"id", "name", "aliases", "adapter"}:
            raise ValueError("Locations require id, name, aliases and adapter")
        if (
            not isinstance(item["id"], str)
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", item["id"])
            or item["id"] in ids
        ):
            raise ValueError("Location IDs must be unique lowercase slugs")
        if not isinstance(item["name"], str) or not 1 <= len(item["name"].strip()) <= 40:
            raise ValueError("Location names must contain 1–40 characters")
        if (
            not isinstance(item["aliases"], list)
            or len(item["aliases"]) > 8
            or any(not isinstance(a, str) or not 1 <= len(a.strip()) <= 40 for a in item["aliases"])
        ):
            raise ValueError("Use at most eight short location aliases")
        for name in [item["id"], item["name"], *item["aliases"]]:
            key = normalized(name)
            if not key or (key in names and names[key] != item["id"]):
                raise ValueError("Location names/aliases must be unambiguous")
            names[key] = item["id"]
        ids.add(item["id"])
        adapters.append(item["adapter"])
    if sorted(adapters) != ["cast", "pi"]:
        raise ValueError("This prototype supports one Pi and one Cast adapter")
    if settings["travel_side"] not in ("left", "right"):
        raise ValueError("travel_side must be left or right")
    duration = settings["duration_seconds"]
    if type(duration) not in (int, float) or not 0.5 <= duration <= 5:
        raise ValueError("Movement duration must be 0.5–5 seconds")
    if (
        settings["lab"]["theme"] != "pixel-lab"
        or not isinstance(settings["lab"]["title"], str)
        or not 1 <= len(settings["lab"]["title"].strip()) <= 40
    ):
        raise ValueError("Use the pixel-lab theme and a short lab title")


def configured():
    from .config import get_config

    from .surface_registry import Registry

    return Registry().enrich(copy.deepcopy(get_config()["surfaces"]["locations"]))


def for_adapter(adapter):
    return next(item for item in configured() if item["adapter"] == adapter)


def destination(text):
    """Resolve only configured names, prioritizing an explicit destination clause."""
    value = normalized(text)
    clauses = re.split(r"\b(?:to|onto|at)\b", value)
    candidates = [clauses[-1]] if len(clauses) > 1 else [value]
    for candidate in candidates:
        found = {
            item["id"]
            for item in configured()
            if any(
                re.search(r"(?<!\w)" + re.escape(normalized(name)) + r"(?!\w)", candidate)
                for name in [item["id"], item["name"], *item["aliases"]]
            )
        }
        if len(found) == 1:
            return found.pop()
    return None


def movement_request(text):
    return bool(re.search(MOVE_VERB, text, re.I)) and destination(text) is not None

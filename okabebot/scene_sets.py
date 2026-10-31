"""Scene identity belongs to a physical location; presentation is only its view."""

from .characters import registry, get

CATALOG = {
    "presentations": {"room": "Room", "companion": "Companion"},
    "characters": {key: list(value.scenes()) for key, value in registry().items()},
    "sets": {
        key: value for character in registry().values() for key, value in character.scenes().items()
    },
}


def validate_selection(character, selected):
    if character not in CATALOG["characters"]:
        raise ValueError("Unknown scene character")
    if selected is not None and selected not in CATALOG["characters"][character]:
        raise ValueError("Choose one of this character's scene sets")


def environment(place, character, enabled=True):
    selected = place.get("scene_selections", {}).get(character)
    if not enabled:
        selected = get(character).definition["default_scene"]
    return {
        "set": selected,
        "name": CATALOG["sets"].get(selected, {}).get("name", "Unassigned"),
        "presentation": place.get("presentation", "companion"),
        "assigned": selected is not None,
    }

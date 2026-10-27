"""Scene identity belongs to a physical location; presentation is only its view."""

import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent / "assets/scene-sets.json").read_text())


def validate_selection(character, selected):
    if character not in CATALOG["characters"]:
        raise ValueError("Unknown scene character")
    if selected is not None and selected not in CATALOG["characters"][character]:
        raise ValueError("Choose one of this character's scene sets")


def environment(place, character, enabled=True):
    selected = place.get("scene_selections", {}).get(character)
    if not enabled:
        selected = "green-hill" if character == "sonic" else "pixel-lab"
    return {
        "set": selected,
        "name": CATALOG["sets"].get(selected, {}).get("name", "Unassigned"),
        "presentation": place.get("presentation", "companion"),
        "assigned": selected is not None,
    }

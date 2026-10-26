"""Competition context shared by title parsing and verified team enrichment."""

import json
from pathlib import Path
import re

LEAGUES = json.loads((Path(__file__).parent / "assets/leagues.json").read_text())


def detect(text):
    matches = [
        league
        for league in LEAGUES
        if any(
            re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text)
            for alias in league["aliases"]
        )
    ]
    return matches[0] if len(matches) == 1 else None


def matches(identifier, labels):
    league = next((value for value in LEAGUES if value["id"] == identifier), None)
    if not league:
        return False
    aliases = set(league["aliases"] + [league["name"].casefold()])
    normalized = {re.sub(r"[^\w]+", " ", label.casefold()).strip() for label in labels}
    return bool(aliases & normalized)

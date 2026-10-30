"""Resolve owner chat's explicitly selected or paired browser location."""

import re
from . import locations


def resolve(surfaces, data):
    places = surfaces.snapshot()["locations"]
    approved = {p["id"]: p for p in places if p.get("approved")}
    identity = data.get("location_id")
    if identity:
        if identity not in approved:
            raise ValueError("Choose an approved dashboard location")
        return approved[identity]
    secret = data.get("surface_secret")
    if secret:
        try:
            place = surfaces.registered(secret)
            return approved.get(place.get("id")) if isinstance(place, dict) else None
        except (PermissionError, ValueError):
            pass
    return None


def ground(text, place):
    # Only explicit movement uses here as a target. Never guess the occupied room.
    if re.search(locations.MOVE_VERB, text, re.I) and re.search(
        r"\b(here|this screen|this device)\b", text, re.I
    ):
        if place is None:
            raise ValueError(
                "Choose where this dashboard is, or open its paired companion page first"
            )
        return re.sub(
            r"\b(here|this screen|this device)\b", lambda _: place["id"], text, flags=re.I
        )
    return text

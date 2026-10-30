"""Read-only context adapters. Registry metadata drives setup, validation and polling."""

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class Feed:
    id: str
    label: str
    transport: str
    fields: tuple  # (configuration key, label, entity domain / free text)
    item_fields: tuple
    instructions: str
    interval: int = 300
    freshness: int = 900
    household: bool = False


# Agency GTFS identifiers verified against Sound Transit's rail routes.txt.
# Provider identifiers are adapter-owned, never household configuration.
LINE_ROUTES = {
    "1": ("100479", "1-SHUTTLE"),
    "2": ("2LINE", "2-SHUTTLE"),
    "T": ("TLINE",),
    "N": ("SNDR_EV",),
    "S": ("SNDR_TL",),
}

FEEDS = {
    f.id: f
    for f in (
        Feed(
            "tasks",
            "Tasks · Local To-do / Google Tasks",
            "ha",
            (("entities", "To-do entity IDs", "todo"),),
            ("id", "title", "state", "due", "list"),
            "Add Local To-do or Google Tasks in Home Assistant. Select only the lists to observe.",
        ),
        Feed(
            "device_activity",
            "Device activity · charging, focus, lock",
            "ha",
            (
                ("charging", "Charging binary sensors", "binary_sensor"),
                ("focus", "Focus binary sensors", "binary_sensor"),
                ("locked", "Device-locked binary sensors", "binary_sensor"),
                ("screen", "Display-awake binary sensors", "binary_sensor"),
            ),
            ("id", "signal", "state"),
            "Enable selected Companion app sensors; use binary sensors only. No app names, GPS or keystrokes.",
        ),
        Feed(
            "appliances",
            "LG ThinQ · appliance status",
            "ha",
            (("entities", "Appliance status / error sensor IDs", "sensor"),),
            ("id", "label", "state", "unit"),
            "Connect LG ThinQ in Home Assistant, then select cycle/status/error sensors. LG uses its cloud.",
            household=True,
        ),
        Feed(
            "meals",
            "Mealie · meal plans and shopping",
            "ha",
            (
                ("calendars", "Meal-plan calendar IDs", "calendar"),
                ("shopping", "Shopping to-do IDs", "todo"),
            ),
            ("id", "title", "category", "start", "end", "state", "due", "list"),
            "Connect your self-hosted Mealie to Home Assistant. Plans and shopping lists do not prove pantry stock.",
            household=True,
        ),
        Feed(
            "transit",
            "Sound Transit · rail service alerts",
            "sound_transit",
            (("routes", "Rail lines: 1, 2, T, N, S (blank = all)", "line"),),
            ("id", "title", "effect", "routes", "end_at"),
            "Public feed; no account required. Covers 1/2/T Line and N/S Sounder. Alerts are not live arrival predictions.",
            freshness=600,
            household=True,
        ),
        Feed(
            "watch_history",
            "Trakt · confirmed watch history",
            "trakt",
            (),
            ("id", "title", "type", "watched_at", "show"),
            "Save a Trakt client ID and access token here (or in private .env). Read-only recent history; no streaming passwords.",
            interval=1800,
            freshness=7200,
        ),
    )
}


def validate_config(feed, value):
    if not isinstance(value, dict) or set(value) != {"enabled", *(f[0] for f in feed.fields)}:
        raise ValueError("Use declared feed configuration")
    if type(value["enabled"]) is not bool:
        raise ValueError("Choose enabled or disabled")
    for key, _, domain in feed.fields:
        entries = value[key]
        if (
            not isinstance(entries, list)
            or len(entries) > 1000
            or len(set(entries)) != len(entries)
        ):
            raise ValueError(
                "Choose unique entity/route identifiers (maximum 1000 per field for request safety)"
            )
        for entry in entries:
            if not isinstance(entry, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", entry):
                raise ValueError("Use bounded entity/route identifiers")
            if domain == "line" and entry not in LINE_ROUTES:
                raise ValueError("Choose a supported rail line")
            if domain not in ("text", "line") and not entry.startswith(domain + "."):
                raise ValueError("Wrong Home Assistant entity domain")
    if value["enabled"] and feed.transport == "ha" and not any(value[f[0]] for f in feed.fields):
        raise ValueError("Select at least one entity")
    return value


def validate_snapshot(payload):
    if not isinstance(payload, dict) or set(payload) != {
        "provider",
        "items",
        "complete",
        "valid_until_at",
    }:
        raise ValueError("Invalid feed snapshot")
    feed = FEEDS.get(payload["provider"])
    if not feed or payload["complete"] not in ("yes", "no"):
        raise ValueError("Unknown feed")
    stamp = payload["valid_until_at"]
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError("Invalid feed freshness")
    items = payload["items"]
    if not isinstance(items, list) or len(items) > 20:
        raise ValueError("Bounded feed items required")
    for item in items:
        if not isinstance(item, dict) or not item.get("id") or set(item) - set(feed.item_fields):
            raise ValueError("Invalid normalized item")
        for key, value in item.items():
            if key.endswith("_at"):
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid item time")
            elif not isinstance(value, str) or not 1 <= len(value) <= 200:
                raise ValueError("Use bounded text metadata")

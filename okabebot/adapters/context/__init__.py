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
            "presence_history",
            "Presence history · selected people and zones",
            "ha",
            (("persons", "Person entities", "person"), ("zones", "Zone counts", "zone")),
            ("id", "entity_key", "label", "state", "source_type", "observation", "reported_at"),
            "Read selected HA presence reports in a bounded three-UTC-day window, without coordinates. Zone counts do not identify who left; unknown is not away. Departure reports are not proof of physical movement.",
            interval=60,
            freshness=180,
            household=True,
        ),
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
            "health",
            "Health · selected daily wellbeing signals",
            "ha",
            (
                ("daily_steps", "Daily steps (one daily-reset source)", "sensor"),
                ("sleep_minutes", "Sleep duration in minutes (one source)", "sensor"),
                ("active_minutes", "Daily active minutes (one source)", "sensor"),
                ("others", "Other people detected (optional binary sensors)", "binary_sensor"),
            ),
            ("id", "metric", "value", "unit", "sample_at"),
            "Private, opt-in readings only. Choose daily-reset totals, not steps since reboot. No heart rate, weight, diagnosis or sleep-confidence inference. Others detected suppresses health discussion; unknown bound occupancy also suppresses it. Goals and coaching are separate choices.",
            interval=300,
            freshness=900,
        ),
        Feed(
            "room_activity",
            "Room activity · lights, switches and speakers",
            "ha",
            (
                ("lights", "Light entities", "light"),
                ("switches", "Light-switch entities", "switch"),
                ("players", "Speaker / media player entities", "media_player"),
            ),
            ("id", "label", "state", "category", "room"),
            "Read selected device states only; no track titles, brightness, volume or commands. Activity is not proof of occupancy or identity. Selected playing/unknown speaker states defer proactive check-ins.",
            interval=60,
            freshness=150,
            household=True,
        ),
        Feed(
            "home_devices",
            "Home devices · garage doors and thermostats",
            "ha",
            (
                ("covers", "Door / cover entities", "cover"),
                ("climates", "Thermostat entities", "climate"),
                ("sensors", "Related status / temperature sensors", "sensor"),
            ),
            (
                "id",
                "label",
                "state",
                "unit",
                "category",
                "current_temperature",
                "target_temperature",
                "action",
                "room",
            ),
            "Select existing HA devices for read-only state context. Door state does not identify a person or trigger arrival. No open/close or heating commands.",
            household=True,
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
            "Trakt · history and selected watched lists",
            "trakt",
            (),
            (
                "id",
                "title",
                "type",
                "watched_at",
                "show",
                "watch_state",
                "provenance",
                "list_id",
                "trakt_id",
            ),
            "Read a configured recent-history window and explicitly selected owned lists marked watched with unknown dates. List membership never supplies a watched date or streaming entitlement.",
            interval=1800,
            freshness=7200,
        ),
    )
}


TRAKT_DEFAULTS = {"history_days": 30, "page_budget": 1, "watched_lists": []}
TRAKT_OPTIONS = (
    {
        "key": "history_days",
        "label": "History window (days)",
        "type": "number",
        "min": 1,
        "max": 365,
        "default": 30,
    },
    {
        "key": "page_budget",
        "label": "Maximum pages per polling cycle",
        "type": "number",
        "min": 1,
        "max": 20,
        "default": 1,
    },
    {
        "key": "watched_lists",
        "label": "Watched — date unknown lists",
        "type": "trakt_lists",
        "default": [],
    },
)


def validate_config(feed, value):
    if feed.id == "watch_history" and isinstance(value, dict):
        if set(value) - {"enabled", *TRAKT_DEFAULTS}:
            raise ValueError("Use declared Trakt collection settings")
        value = {**TRAKT_DEFAULTS, "watched_lists": [], **value}
        if type(value["history_days"]) is not int or not 1 <= value["history_days"] <= 365:
            raise ValueError("Choose a history window from 1 to 365 days")
        if type(value["page_budget"]) is not int or not 1 <= value["page_budget"] <= 20:
            raise ValueError("Choose a page budget from 1 to 20")
        lists = value["watched_lists"]
        if (
            not isinstance(lists, list)
            or len(lists) > 19
            or any(
                not isinstance(v, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", v) for v in lists
            )
            or len(set(lists)) != len(lists)
        ):
            raise ValueError("Choose up to 19 distinct owned Trakt list IDs")
        if value["page_budget"] < 1 + len(lists):
            raise ValueError("Page budget must allow one page for history and each selected list")
        expected = {"enabled", *TRAKT_DEFAULTS}
    else:
        expected = {"enabled", *(f[0] for f in feed.fields)}
    if not isinstance(value, dict) or set(value) != expected:
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
    if feed.id == "health" and any(
        len(value[k]) > 1 for k in ("daily_steps", "sleep_minutes", "active_minutes")
    ):
        raise ValueError("Choose one source per health metric to avoid double counting")
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

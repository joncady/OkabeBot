"""Private, deterministic morning preparation; never infers sleep or generates speech."""

from datetime import datetime
import json
import math
from zoneinfo import ZoneInfo

from .amadeus import Store
from .amadeus_onboarding import SYSTEM, KEY
from .amadeus_sources import Collector, digest, text

CONFIG_KEY = "morning.config"
DEFAULTS = {
    "enabled": False,
    "start_hour": 4,
    "end_hour": 12,
    "temperature_unit": "°C",
    "destination": "",
    "present_on_wake": False,
    "before_minutes": 30,
    "after_minutes": 90,
    "rotation_seconds": 12,
    "display_minutes": 120,
}


def validate(value, locations):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError("Provide morning configuration fields")
    for key in ("enabled", "present_on_wake"):
        if type(value[key]) is not bool:
            raise ValueError("Use boolean morning controls")
    for key, low, high in (
        ("start_hour", 0, 23),
        ("end_hour", 1, 24),
        ("before_minutes", 0, 180),
        ("after_minutes", 1, 240),
        ("rotation_seconds", 5, 60),
        ("display_minutes", 5, 240),
    ):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError("Morning interval outside supported range")
    if value["start_hour"] >= value["end_hour"] or value["temperature_unit"] not in ("°C", "°F"):
        raise ValueError("Choose a daytime window and temperature unit")
    targets = {p["id"] for p in locations if p.get("adapter") == "cast"}
    if value["destination"] != "" and value["destination"] not in targets:
        raise ValueError("Choose a configured TV destination")
    if value["present_on_wake"] and not value["destination"]:
        raise ValueError("Automatic presentation requires a TV destination")
    return dict(value)


class Morning:
    def __init__(self, folder, *, clock=None):
        self.folder = folder
        self.clock = clock

    def store(self):
        return Store(
            self.folder,
            sources=["phone_context", "weather"],
            **({"clock": self.clock} if self.clock else {}),
        )

    @staticmethod
    def preference(store, key, default=None):
        row = store.db.execute(
            "SELECT value FROM preferences WHERE subject=? AND key=?", (SYSTEM, key)
        ).fetchone()
        return json.loads(row[0]) if row else default

    def settings(self):
        store = self.store()
        try:
            return self.preference(store, CONFIG_KEY, dict(DEFAULTS))
        finally:
            store.close()

    def configure(self, value, locations):
        value = validate(value, locations)
        store = self.store()
        try:
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                if not self.preference(store, KEY):
                    raise ValueError("Save private setup first")
                store.remember(SYSTEM, CONFIG_KEY, value)
            return value
        finally:
            store.close()

    def observe(self, data):
        if not isinstance(data, dict) or set(data) != {
            "entity_id",
            "state",
            "event_id",
            "observed_at",
            "details",
        }:
            raise ValueError("Invalid morning source envelope")
        if (
            not isinstance(data["entity_id"], str)
            or not isinstance(data["state"], str)
            or len(data["state"]) > 512
        ):
            raise ValueError("Use bounded source fields")
        if not isinstance(data["event_id"], str) or not 1 <= len(data["event_id"]) <= 128:
            raise ValueError("Invalid source ID")
        store = self.store()
        now = store.clock()
        store.close()
        at = data["observed_at"]
        if type(at) not in (int, float) or not 0 <= now - at <= 60:
            raise ValueError("Stale source event")
        from pathlib import Path

        bindings = json.loads((Path(self.folder) / "ha-bindings.json").read_text())
        entity = data["entity_id"]
        if entity in bindings.get("interactive", []):
            kind, source = "phone_wake", "phone_context"
            if (
                data["state"] not in ("on", "off")
                or not isinstance(data["details"], dict)
                or set(data["details"]) != {"previous_state"}
                or data["details"]["previous_state"] not in ("on", "off")
                or data["details"]["previous_state"] == data["state"]
            ):
                raise ValueError("Invalid screen state")
            payload = {"state": data["state"]}
        elif entity in bindings.get("alarm", []):
            kind, source = "phone_alarm", "phone_context"
            if data["details"] != {}:
                raise ValueError("Unexpected alarm metadata")
            alarm = (
                0
                if data["state"] in ("unknown", "unavailable", "none")
                else datetime.fromisoformat(data["state"].replace("Z", "+00:00"))
            )
            if alarm and alarm.tzinfo is None:
                raise ValueError("Alarm must have a timezone")
            payload = {"alarm_at": alarm.timestamp() if alarm else 0}
        elif entity in bindings.get("weather", []):
            kind, source = "weather", "weather"
            details = data["details"]
            if not isinstance(details, dict) or set(details) != {
                "temperature",
                "unit",
                "updated_at",
            }:
                raise ValueError("Invalid weather fields")
            t, updated = details["temperature"], details["updated_at"]
            if (
                type(t) not in (int, float)
                or not math.isfinite(t)
                or details["unit"] not in ("°C", "°F")
            ):
                raise ValueError("Invalid weather measurement")
            if (
                type(updated) not in (int, float)
                or not 0 <= now - updated <= 3 * 3600
                or data["state"] in ("unknown", "unavailable")
            ):
                raise ValueError("Stale weather")
            temperature = t if details["unit"] == "°C" else (t - 32) * 5 / 9
            if not -100 <= temperature <= 100:
                raise ValueError("Weather temperature outside supported range")
            payload = {
                "condition": text(data["state"]),
                "temperature_c": temperature,
                "reported_at": updated,
            }
        else:
            raise PermissionError("Unbound morning source")
        collector = Collector(self.folder, **({"clock": self.clock} if self.clock else {}))
        result = collector._record(
            source,
            lambda _: [
                (
                    kind,
                    payload,
                    "profile" if source == "phone_context" else "household",
                    digest([entity, data["event_id"], kind]),
                    at,
                )
            ],
        )
        if kind == "phone_wake" and payload["state"] == "on" and result["state"] == "stored":
            result["prepared"] = self.prepare(at)
        return result

    @staticmethod
    def permitted(settings, config):
        return bool(
            settings
            and config["enabled"]
            and not settings["paused"]
            and not settings["guest"]
            and "phone_context" in settings["sources"]
        )

    def prepare(self, at):
        store = self.store()
        try:
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                settings = self.preference(store, KEY)
                config = self.preference(store, CONFIG_KEY, DEFAULTS)
                if not self.permitted(settings, config):
                    return False
                local = datetime.fromtimestamp(at, ZoneInfo(settings["timezone"]))
                if not config["start_hour"] <= local.hour < config["end_hour"]:
                    return False
                day = local.date().isoformat()
                external = "morning:" + settings["profile"] + ":" + day
                if store.db.execute(
                    "SELECT 1 FROM events WHERE source='phone_context' AND external_id=?",
                    (external,),
                ).fetchone():
                    return False
                # Keep recent alarm observations when Android advances after dismissal.
                rows = store.db.execute(
                    "SELECT payload,observed_at FROM events WHERE source='phone_context' AND kind='phone_alarm' AND subject=? AND expires_at>? AND observed_at<=? AND observed_at>? ORDER BY observed_at DESC LIMIT 500",
                    (settings["profile"], store.clock(), at, at - 86400),
                ).fetchall()
                alarms = []
                newer = []
                for row in rows:
                    alarm = json.loads(row["payload"])["alarm_at"]
                    replaced = next((r for a, r in reversed(newer) if a != alarm), None)
                    # Preserve dismissal/rollover near the scheduled alarm, but not
                    # an alarm replaced or canceled well before its wake window.
                    if replaced is None or replaced >= alarm - config["before_minutes"] * 60:
                        alarms.append(alarm)
                    newer.append((alarm, row["observed_at"]))
                if not any(
                    a > 0
                    and -config["before_minutes"] * 60 <= at - a <= config["after_minutes"] * 60
                    for a in alarms
                ):
                    return False
                store.retention = settings["retention_days"] * 86400
                store.observe(
                    source="phone_context",
                    external_id=external,
                    subject=settings["profile"],
                    kind="morning_summary",
                    observed_at=at,
                    payload={
                        "day": day,
                        "target": config["destination"] or "unassigned",
                        "until_at": at + config["display_minutes"] * 60,
                    },
                )
                return True
        finally:
            store.close()

    def view(self, destination=None, *, preview=False):
        store = self.store()
        try:
            settings = self.preference(store, KEY)
            config = self.preference(store, CONFIG_KEY, DEFAULTS)
            if not self.permitted(settings, config):
                return None
            row = store.db.execute(
                "SELECT payload,observed_at FROM events WHERE kind='morning_summary' AND subject=? AND expires_at>? ORDER BY observed_at DESC LIMIT 1",
                (settings["profile"], store.clock()),
            ).fetchone()
            if not preview:
                if not row:
                    return None
                run = json.loads(row[0])
                if (
                    run["until_at"] <= store.clock()
                    or run["target"] != destination
                    or config["destination"] != destination
                ):
                    return None
            cards = []
            if "weather" in settings["sources"]:
                weather = store.db.execute(
                    "SELECT payload FROM events WHERE source='weather' AND kind='weather' AND subject='unknown' AND expires_at>? ORDER BY observed_at DESC LIMIT 1",
                    (store.clock(),),
                ).fetchone()
                if weather:
                    value = json.loads(weather[0])
                    if 0 <= store.clock() - value["reported_at"] <= 3 * 3600:
                        cards.append(
                            {
                                "kind": "weather",
                                "title": "Outside",
                                "body": value["condition"].replace("-", " ")
                                + " · "
                                + str(
                                    round(
                                        value["temperature_c"]
                                        if config["temperature_unit"] == "°C"
                                        else value["temperature_c"] * 9 / 5 + 32
                                    )
                                )
                                + config["temperature_unit"],
                            }
                        )
            if not cards:
                cards.append(
                    {"kind": "weather", "title": "Outside", "body": "Weather not available yet"}
                )
            if "calendar" in settings["sources"]:
                marker = store.db.execute(
                    "SELECT payload,observed_at FROM events WHERE kind='calendar_snapshot' AND subject=? AND expires_at>? ORDER BY observed_at DESC LIMIT 1",
                    (settings["profile"], store.clock()),
                ).fetchone()
                if marker and 0 <= store.clock() - json.loads(marker["payload"])["start_at"] <= 600:
                    snapshot = json.loads(marker["payload"])
                    events = store.db.execute(
                        "SELECT payload FROM events WHERE kind='calendar' AND subject=? AND expires_at>? AND observed_at>=?",
                        (
                            settings["profile"],
                            store.clock(),
                            math.floor(snapshot["start_at"] / 300) * 300,
                        ),
                    ).fetchall()
                    values = [json.loads(r[0]) for r in events]
                    today = datetime.fromtimestamp(
                        store.clock(), ZoneInfo(settings["timezone"])
                    ).date()
                    values = sorted(
                        (
                            v
                            for v in values
                            if v.get("snapshot_id") == snapshot["snapshot_id"]
                            and v["start_at"] > store.clock()
                            and datetime.fromtimestamp(
                                v["start_at"], ZoneInfo(settings["timezone"])
                            ).date()
                            == today
                        ),
                        key=lambda v: v["start_at"],
                    )
                    for v in values[:5]:
                        cards.append(
                            {
                                "kind": "calendar",
                                "title": datetime.fromtimestamp(
                                    v["start_at"], ZoneInfo(settings["timezone"])
                                ).strftime("%H:%M"),
                                "body": v["summary"],
                            }
                        )
                    if not values:
                        cards.append(
                            {
                                "kind": "calendar",
                                "title": "Today",
                                "body": "No upcoming timed events in this feed",
                            }
                        )
                else:
                    cards.append(
                        {
                            "kind": "calendar",
                            "title": "Today",
                            "body": "Calendar is waiting for a fresh update",
                        }
                    )
            return {
                "title": "Good morning",
                "rotation_seconds": config["rotation_seconds"],
                "cards": cards,
                "prepared_at": row["observed_at"] if row else store.clock(),
            }
        finally:
            store.close()

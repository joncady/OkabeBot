"""Bounded HTTP readers and pure provider normalizers; no device actions."""

from datetime import datetime, timezone, timedelta
import hashlib
import json
from . import LINE_ROUTES
from ...spotify import env_value
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

SOUND_TRANSIT_URL = "https://s3.amazonaws.com/st-service-alerts-prod/alerts_pb.json"


def clean(value, limit=200):
    return "".join(c for c in str(value or "") if ord(c) >= 32)[:limit].strip()


def identity(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:32]


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Provider redirects are not permitted")


def request(url, headers=None, data=None):
    parts = urlsplit(url)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Use an explicit HTTP(S) provider URL without credentials")
    req = Request(
        url, headers=headers or {}, data=None if data is None else json.dumps(data).encode()
    )
    with build_opener(NoRedirect()).open(req, timeout=10) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Provider response too large")
    return json.loads(raw)


class HomeAssistant:
    def __init__(self, read=request, connection=None):
        self.read = read
        self.connection = connection or {}

    def call(self, path, data=None):
        base = (self.connection.get("url") or env_value("AMADEUS_HA_URL")).rstrip("/")
        token = self.connection.get("token") or env_value("AMADEUS_HA_TOKEN")
        if not base or not token:
            raise ValueError("Home Assistant credentials required")
        # Configured base only, fixed API paths; never follow upstream URLs.
        if urlsplit(base).query or urlsplit(base).fragment:
            raise ValueError("Use a Home Assistant origin")
        return self.read(
            base + "/api/" + path,
            {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            data,
        )

    def todos(self, entity):
        value = self.call("services/todo/get_items?return_response", {"entity_id": entity})
        return value["service_response"][entity]["items"]

    def read_feed(self, feed, cfg, now):
        items = []
        if feed.id in ("tasks", "meals"):
            for entity in cfg.get("entities", []) + cfg.get("shopping", []):
                label = clean(
                    self.call("states/" + quote(entity, safe=""))
                    .get("attributes", {})
                    .get("friendly_name", "To-do list")
                )
                for item in self.todos(entity):
                    normalized = {
                        "id": identity([entity, item["uid"]]),
                        "title": clean(item["summary"]),
                        "state": clean(item["status"]),
                        "list": label,
                    }
                    if item.get("due"):
                        normalized["due"] = clean(item["due"])
                    if feed.id == "meals":
                        normalized["category"] = "shopping"
                    items.append(normalized)
            for entity in cfg.get("calendars", []):
                start = datetime.fromtimestamp(now, timezone.utc)
                query = urlencode(
                    {"start": start.isoformat(), "end": (start + timedelta(days=2)).isoformat()}
                )
                for item in self.call("calendars/" + quote(entity, safe="") + "?" + query):
                    normalized = {
                        "id": identity([entity, item.get("uid"), item["start"], item["summary"]]),
                        "title": clean(item["summary"]),
                        "category": "meal_plan",
                        "start": clean(item["start"].get("dateTime", item["start"].get("date"))),
                        "end": clean(item["end"].get("dateTime", item["end"].get("date"))),
                    }
                    items.append(normalized)
        elif feed.id == "device_activity":
            for signal in ("charging", "focus", "locked", "screen"):
                for entity in cfg.get(signal, []):
                    value = self.call("states/" + quote(entity, safe=""))
                    state = value["state"]
                    items.append(
                        {
                            "id": identity([entity, signal]),
                            "signal": signal,
                            "state": state if state in ("on", "off") else "unknown",
                        }
                    )
        else:
            for entity in cfg["entities"]:
                value = self.call("states/" + quote(entity, safe=""))
                items.append(
                    {
                        "id": identity(entity),
                        "label": clean(
                            value.get("attributes", {}).get("friendly_name", "Appliance")
                        ),
                        "state": clean(value["state"]),
                        **(
                            {"unit": clean(value.get("attributes", {}).get("unit_of_measurement"))}
                            if value.get("attributes", {}).get("unit_of_measurement")
                            else {}
                        ),
                    }
                )
        return items, True


def transit(value, cfg, now):
    # Reject stale or unexpectedly future upstream feeds, even if HTTP is healthy.
    checked = float(value["header"]["timestamp"])
    if not 0 <= now - checked <= 900:
        raise ValueError("Stale transit feed")
    items = []
    for entity in value.get("entity", []):
        if entity.get("is_deleted"):
            continue
        alert = entity.get("alert", {})
        selectors = alert.get("informed_entity", [])
        routes = sorted({s["route_id"] for s in selectors if s.get("route_id")})
        # Blank filter means all rail in this rail-only authority feed.
        selected = {route for line in cfg["routes"] for route in LINE_ROUTES[line]}
        if selected and routes and not set(routes).intersection(selected):
            continue
        periods = alert.get("active_period", [])
        active = [
            p for p in periods if float(p.get("start", 0)) <= now < float(p.get("end", now + 600))
        ]
        if periods and not active:
            continue
        translations = alert.get("header_text", {}).get("translation", [])
        title = next(
            (t.get("text") for t in translations if t.get("language", "").startswith("en")),
            translations[0].get("text") if translations else "",
        )
        if not title:
            continue
        # Never invent route names from literal title matching.
        item = {
            "id": identity(entity["id"]),
            "title": clean(title),
            "effect": clean(alert.get("effect", "UNKNOWN_EFFECT")),
            "routes": clean(
                ", ".join(
                    line + " Line"
                    for line, ids in LINE_ROUTES.items()
                    if set(ids).intersection(routes)
                )
                or "Agency-wide"
            ),
        }
        if active and all(p.get("end") for p in active):
            item["end_at"] = max(float(p["end"]) for p in active)
        items.append(item)
    priority = {"NO_SERVICE": 0, "SIGNIFICANT_DELAYS": 1, "REDUCED_SERVICE": 2, "DETOUR": 3}
    items.sort(key=lambda item: (priority.get(item["effect"], 9), item["id"]))
    return items, True


def trakt(value, now):
    if not isinstance(value, list):
        raise ValueError("Invalid history response")
    items = []
    for entry in value:
        kind = entry["type"]
        if kind not in ("movie", "episode"):
            continue
        watched = stamp(entry["watched_at"])
        if not now - 30 * 86400 <= watched <= now:
            continue
        media = entry[kind]
        item = {
            "id": identity(entry["id"]),
            "title": clean(media["title"]),
            "type": kind,
            "watched_at": watched,
        }
        if kind == "episode" and entry.get("show", {}).get("title"):
            item["show"] = clean(entry["show"]["title"])
        items.append(item)
    # Bounded page, not a claim of complete account history.
    return items, False


def fetch(feed, cfg, now, connection=None):
    connection = connection or {}
    if feed.transport == "ha":
        return HomeAssistant(connection=connection).read_feed(feed, cfg, now)
    if feed.transport == "sound_transit":
        return transit(request(SOUND_TRANSIT_URL), cfg, now)
    if feed.transport == "trakt":
        client = connection.get("client_id") or env_value("AMADEUS_TRAKT_CLIENT_ID")
        token = connection.get("token") or env_value("AMADEUS_TRAKT_ACCESS_TOKEN")
        if not client or not token:
            raise ValueError("Trakt authorization required")
        query = urlencode(
            {
                "limit": 100,
                "page": 1,
                "start_at": datetime.fromtimestamp(now - 30 * 86400, timezone.utc).isoformat(),
            }
        )
        return trakt(
            request(
                "https://api.trakt.tv/sync/history?" + query,
                {
                    "Authorization": "Bearer " + token,
                    "trakt-api-key": client,
                    "trakt-api-version": "2",
                    "User-Agent": "OkabeBot/0.1.0",
                },
            ),
            now,
        )
    raise ValueError("Unknown feed transport")

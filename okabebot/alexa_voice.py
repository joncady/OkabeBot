"""Fresh, allowlisted Alexa history events -> structured companion actions only."""

import datetime as dt
import hmac
import json
import math
import re
import sqlite3
import time
from urllib.parse import urlsplit

from .integration_auth import persistent_token
from .locations import normalized


def validate(settings):
    if type(settings["enabled"]) is not bool:
        raise ValueError("Alexa voice enabled must be boolean")
    if not isinstance(settings["devices"], list) or len(settings["devices"]) > 20:
        raise ValueError("Use a short explicit Alexa device allowlist")
    seen = set()
    for device in settings["devices"]:
        if (
            not isinstance(device, dict)
            or set(device) != {"entity_id", "default_location"}
            or not isinstance(device["entity_id"], str)
            or not re.fullmatch(r"event\.[a-z0-9_]+_voice_event", device["entity_id"])
            or not isinstance(device["default_location"], str)
            or device["entity_id"] in seen
        ):
            raise ValueError("Alexa devices require a voice-event entity and default location")
        seen.add(device["entity_id"])
    all_phrases = set()
    for key in ("welcome_phrases", "summon_phrases", "move_prefixes"):
        values = settings[key]
        if not isinstance(values, list) or len(values) > 20:
            raise ValueError("Alexa phrases must be short explicit lists")
        for phrase in values:
            if not isinstance(phrase, str) or not 1 <= len(phrase) <= 120:
                raise ValueError("Invalid Alexa phrase")
            text = normalized(phrase)
            if not text or text in all_phrases:
                raise ValueError("Alexa phrases must be distinct")
            all_phrases.add(text)


class AlexaVoice:
    def __init__(self, folder, settings, controller):
        validate(settings)
        self.settings, self.controller = settings, controller
        self.token = persistent_token(folder, "alexa-voice-token")
        self.path = folder / "alexa-voice-events.sqlite3"
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, created REAL, source_at REAL)"
            )
            if "source_at" not in {row[1] for row in db.execute("PRAGMA table_info(events)")}:
                db.execute("ALTER TABLE events ADD COLUMN source_at REAL")
            # Older ledgers used receipt time. Keep it as a conservative barrier
            # rather than replaying a just-handled command during migration.
            db.execute("UPDATE events SET source_at=created WHERE source_at IS NULL")
        self.path.chmod(0o600)

    def parse(self, command, device):
        value = normalized(command)
        if value in {normalized(p) for p in self.settings["welcome_phrases"]}:
            return "welcome", None
        destination = (
            device["default_location"]
            if value in {normalized(p) for p in self.settings["summon_phrases"]}
            else None
        )
        if destination is None:
            tails = [
                value[len(normalized(p)) + 1 :]
                for p in self.settings["move_prefixes"]
                if value.startswith(normalized(p) + " ")
            ]
            if not tails:
                return None
            destination = tails[0]
        if normalized(destination).startswith("the "):
            destination = normalized(destination)[4:]
        places = self.controller.surfaces.snapshot()["locations"]
        matches = [
            p
            for p in places
            if p.get("approved", True)
            and any(
                normalized(destination) == normalized(name)
                for name in [p["id"], p["name"], *p.get("aliases", [])]
            )
        ]
        if len(matches) != 1:
            raise ValueError("Use one registered companion destination")
        return "move", matches[0]["id"]

    def receive(self, data):
        if not self.settings["enabled"]:
            raise PermissionError("Alexa voice commands are disabled")
        if not isinstance(data, dict) or set(data) != {"entity_id", "occurred_at", "command"}:
            raise ValueError("Invalid Alexa event")
        device = next(
            (d for d in self.settings["devices"] if d["entity_id"] == data["entity_id"]), None
        )
        if device is None:
            raise PermissionError("Alexa device not allowed")
        stamp, command = data["occurred_at"], data["command"]
        if (
            type(stamp) not in (int, float)
            or not math.isfinite(stamp)
            or not 0 <= time.time() - stamp <= 90
            or not isinstance(command, str)
            or not 1 <= len(command) <= 300
        ):
            raise ValueError("Alexa event must be fresh and bounded")
        action = self.parse(command, device)
        if action is None:
            return {"accepted": False, "unmapped": True}
        b = self.controller
        if b.processing or b.recording or b.announcing or (b.codex and b.codex.busy):
            raise ValueError("Companion is busy; no action executed")
        # Timestamp comes from the Alexa event state, not a changing HA context ID.
        # Claim before side effects. An uncertain result must never be retried.
        key = data["entity_id"] + ":" + str(round(stamp * 1000))
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM events WHERE created<?", (time.time() - 86400,))
            prefix = data["entity_id"] + ":"
            previous = db.execute(
                "SELECT MAX(source_at) FROM events WHERE substr(id,1,?)=?",
                (len(prefix), prefix),
            ).fetchone()[0]
            if previous is not None and stamp <= previous:
                return {"accepted": False, "duplicate": True}
            if not db.execute(
                "INSERT OR IGNORE INTO events (id,created,source_at) VALUES (?,?,?)",
                (key, time.time(), stamp),
            ).rowcount:
                return {"accepted": False, "duplicate": True}
        kind, location = action
        if kind == "welcome":
            from .arrival import queue_greeting

            since = (
                dt.datetime.now()
                .astimezone()
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
            )
            item = queue_greeting(
                b.inbox,
                b.notification_policy,
                arrived_at=time.time(),
                trigger="voice",
                recap_since=since,
            )
            return {"accepted": True, "action": kind, "id": item["id"]}
        from .config import get_config

        base = "http://%s:%s" % (get_config()["web"]["host"], b.port)
        result = b.surfaces.move(location, base)
        return {"accepted": bool(result.get("accepted")), "action": kind, "location_id": location}


def handle(handler, bridge):
    if urlsplit(handler.path).path != "/alexa/events":
        return False
    try:
        voice = getattr(bridge, "alexa_voice", None)
        origin = handler.headers.get("Origin")
        if (
            voice is None
            or handler.headers.get("Host") not in bridge.allowed_hosts
            or origin
            and urlsplit(origin).netloc != handler.headers.get("Host")
            or not hmac.compare_digest(handler.headers.get("X-Alexa-Voice-Token", ""), voice.token)
        ):
            raise PermissionError("Forbidden")
        size = int(handler.headers.get("Content-Length", 0))
        if not 0 < size <= 2048:
            raise ValueError("Invalid Alexa event size")
        handler.connection.settimeout(10)
        result = voice.receive(json.loads(handler.rfile.read(size)))
        handler.respond(200, result)
    except PermissionError:
        handler.respond(403, {"error": "Alexa device or integration not authorized"})
    except Exception:
        handler.respond(400, {"error": "Alexa event rejected or action uncertain; do not replay"})
    return True

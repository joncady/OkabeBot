"""Private opt-in morning speech and grounded briefing enrichment."""

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from .amadeus_coaching import Coaching, SETTINGS, DELIVERY, valid_settings
from .amadeus_onboarding import KEY, SYSTEM
from .morning import Morning
from .welcome import validate_intro

MORNING_COACHING = {
    "movement": "Would a short stretch feel good before the day gets busy?",
    "rest": "There is room for a gentle start. No need to rush.",
    "hydration": "If you would like, grab a glass of water to start the day.",
    "meals": "Would planning an easy breakfast make the morning simpler?",
}
VOICE_KEY = "morning.voice"
SPOKEN_KEY = "morning.spoken"
PERSON_KEY = "morning.person"
VOICE_DEFAULTS = {"enabled": False, "name": "", "coaching": False, "quiet_override": False}


def quiet(settings, now):
    clock = datetime.fromtimestamp(now, ZoneInfo(settings["timezone"])).strftime("%H:%M")
    start, end = settings["quiet_start"], settings["quiet_end"]
    return start <= clock < end if start < end else clock >= start or clock < end


class Briefing:
    def __init__(self, folder, *, clock=None):
        self.morning = Morning(folder, clock=clock)

    def person(self, store):
        try:
            entity = json.loads((Path(self.morning.folder) / "ha-bindings.json").read_text()).get(
                "greeting_person"
            )
        except (OSError, ValueError):
            return None
        setup = self.morning.preference(store, KEY)
        value = self.morning.preference(store, PERSON_KEY, {})
        if (
            setup
            and "door_presence" in setup["sources"]
            and value.get("profile") == setup["profile"]
            and value.get("entity_id") == entity
            and 0 <= store.clock() - value.get("observed_at", 0) <= 86400
        ):
            return value
        return None

    def update_person(self, data):
        """Selected HA person display name only; never import tracker/GPS/user attributes."""
        if not isinstance(data, dict) or set(data) != {"entity_id", "name", "observed_at"}:
            raise ValueError("Provide a bounded person name snapshot")
        if not self.valid_name(data["name"]) or not data["name"].strip():
            raise ValueError("Use a short display name")
        binding = json.loads((Path(self.morning.folder) / "ha-bindings.json").read_text())
        if (
            not isinstance(data["entity_id"], str)
            or not data["entity_id"].startswith("person.")
            or data["entity_id"] != binding.get("greeting_person")
        ):
            raise PermissionError("Person is not bound to this private profile")
        store = self.morning.store()
        try:
            stamp = data["observed_at"]
            if type(stamp) not in (int, float) or not 0 <= store.clock() - stamp <= 60:
                raise ValueError("Stale person snapshot")
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                setup = self.morning.preference(store, KEY)
                if (
                    not setup
                    or setup["paused"]
                    or setup["guest"]
                    or "door_presence" not in setup["sources"]
                ):
                    return {"state": "not_permitted"}
                old = self.morning.preference(store, PERSON_KEY, {})
                if old.get("observed_at", 0) > stamp:
                    return {"state": "stale"}
                store.remember(
                    SYSTEM,
                    PERSON_KEY,
                    dict(data, name=data["name"].strip(), profile=setup["profile"]),
                )
            return {"state": "stored"}
        finally:
            store.close()

    @staticmethod
    def valid_name(name):
        return (
            isinstance(name, str)
            and len(name) <= 60
            and all(c.isalpha() or c in " '-." for c in name)
        )

    def settings(self):
        store = self.morning.store()
        try:
            value = dict(VOICE_DEFAULTS, **self.morning.preference(store, VOICE_KEY, {}))
            person = self.person(store)
            return dict(
                value,
                resolved_name=value["name"] or ((person or {}).get("name", "").split() or [""])[0],
                name_source="override"
                if value["name"]
                else "home_assistant"
                if person
                else "unavailable",
                person_entity=(person or {}).get("entity_id", ""),
            )
        finally:
            store.close()

    def configure(self, value):
        if not isinstance(value, dict) or set(value) != set(VOICE_DEFAULTS):
            raise ValueError("Provide morning voice choices")
        if any(type(value[k]) is not bool for k in ("enabled", "coaching", "quiet_override")):
            raise ValueError("Use boolean voice choices")
        name = value["name"]
        if not self.valid_name(name):
            raise ValueError("Use a short spoken name override")
        store = self.morning.store()
        try:
            if not self.morning.preference(store, KEY):
                raise ValueError("Save private setup first")
            if value["enabled"] and not name.strip() and not self.person(store):
                raise ValueError("Link a Home Assistant person or provide a spoken name override")
            store.remember(SYSTEM, VOICE_KEY, dict(value, name=name.strip()))
            return self.settings()
        finally:
            store.close()

    def coaching(self):
        """One owner-authorized morning invitation; no health or habit inference."""
        store = self.morning.store()
        try:
            setup = self.morning.preference(store, KEY)
            voice = self.settings()
            if not self.morning.permitted(setup, self.morning.settings()) or not voice["coaching"]:
                return None
            if quiet(setup, store.clock()) and not voice["quiet_override"]:
                return None
            policy = Coaching(store, timezone=setup["timezone"])
            permission = policy._get(setup["profile"], SETTINGS)
            if (
                not valid_settings(permission)
                or not permission["enabled"]
                or permission["paused_until"] > store.clock()
            ):
                return None
            last = policy._get(setup["profile"], DELIVERY)
            day = datetime.fromtimestamp(store.clock(), ZoneInfo(setup["timezone"])).date()
            if last and not isinstance(last, dict):
                return None
            if last and (
                last.get("day") == day.isoformat()
                or last.get("delivered_at", 0) + 3600 > store.clock()
            ):
                return None
            topics = permission["topics"]
            if not topics:
                return None
            topic = topics[day.toordinal() % len(topics)]
            return {
                "kind": "coaching",
                "title": "A small invitation",
                "body": MORNING_COACHING[topic],
                "topic": topic,
            }
        finally:
            store.close()

    def enrich(self, summary, state=None):
        if summary is None:
            return None
        cards = list(summary["cards"])
        state = state or {}
        attention = sum(
            1
            for n in state.get("notifications", [])
            if isinstance(n, dict)
            and n.get("status") == "pending"
            and n.get("priority") in ("important", "urgent")
        )
        unavailable = sum(
            1
            for v in state.get("device_health", {}).values()
            if isinstance(v, dict) and v.get("available") is False
        )
        if attention:
            cards.append(
                {
                    "kind": "status",
                    "title": "Needs attention",
                    "body": f"{attention} important notification{'s' if attention != 1 else ''} waiting",
                    "important": True,
                }
            )
        if unavailable:
            cards.append(
                {
                    "kind": "status",
                    "title": "Connections",
                    "body": f"{unavailable} device connection{'s' if unavailable != 1 else ''} need attention",
                    "important": True,
                }
            )
        if card := self.coaching():
            cards.append({k: v for k, v in card.items() if k != "topic"})
        return dict(summary, cards=cards)

    def allowed(self, destination):
        if self.morning.view(destination) is None:
            return False
        store = self.morning.store()
        try:
            setup, voice = self.morning.preference(store, KEY), self.settings()
            return bool(
                setup
                and voice["enabled"]
                and voice["resolved_name"]
                and (voice["quiet_override"] or not quiet(setup, store.clock()))
            )
        finally:
            store.close()

    def claim(self, destination):
        """Consume before synthesis/playback; uncertain speech is never auto-replayed."""
        if self.morning.view(destination) is None:
            return False
        store = self.morning.store()
        try:
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                setup = self.morning.preference(store, KEY)
                config = self.morning.preference(store, "morning.config", {})
                voice = dict(VOICE_DEFAULTS, **self.morning.preference(store, VOICE_KEY, {}))
                if (
                    not voice["enabled"]
                    or not (voice["name"] or self.person(store))
                    or not self.morning.permitted(setup, config)
                    or config.get("destination") != destination
                ):
                    return False
                row = store.db.execute(
                    "SELECT payload FROM events WHERE kind='morning_summary' AND subject=? AND expires_at>? ORDER BY observed_at DESC LIMIT 1",
                    (setup["profile"], store.clock()),
                ).fetchone()
                if not row:
                    return False
                run = json.loads(row[0])
                if run["until_at"] <= store.clock() or run["target"] != destination:
                    return False
                if quiet(setup, store.clock()) and not voice["quiet_override"]:
                    return False
                day = (
                    datetime.fromtimestamp(store.clock(), ZoneInfo(setup["timezone"]))
                    .date()
                    .isoformat()
                )
                prior = self.morning.preference(store, SPOKEN_KEY, {})
                if prior.get("day") == day:
                    return False
                store.remember(SYSTEM, SPOKEN_KEY, {"day": day, "state": "claimed"})
                return True
        finally:
            store.close()

    def message(self, summary, character, composer=None):
        name = self.settings()["resolved_name"]
        if not name:
            raise ValueError("No current person name or spoken override")
        intro = f"Good morning, {name}."
        generated = False
        if composer:
            try:
                value = validate_intro(composer(character, name))
                if name.casefold() not in value.casefold() or "morning" not in value.casefold():
                    raise ValueError("Greeting needs morning and configured name")
                intro, generated = value, True
            except InterruptedError:
                raise
            except Exception:
                pass
        # Calendar/notification contents never enter a model or tool-enabled prompt.
        cards = summary["cards"]
        chosen = (
            [c for c in cards if c.get("important")]
            + [c for c in cards if c["kind"] == "calendar"][:2]
            + [c for c in cards if c["kind"] == "weather"][:1]
        )
        coach = self.coaching()
        facts = []
        for card in chosen:
            line = (card.get("spoken") or (card["title"] + ". " + card["body"]))[:130].strip()
            if line and sum(len(x) + 1 for x in facts) + len(line) <= 300:
                facts.append(line.rstrip(".") + ".")
        if coach:
            facts.append(coach["body"])
        return (intro + " " + " ".join(facts))[:550], generated, coach

    def complete(self, *, success, coach=None):
        store = self.morning.store()
        try:
            with store.db:
                value = self.morning.preference(store, SPOKEN_KEY, {})
                if value:
                    store.remember(
                        SYSTEM, SPOKEN_KEY, dict(value, state="delivered" if success else "failed")
                    )
                setup = self.morning.preference(store, KEY)
                if success and coach and setup:
                    Coaching(store, timezone=setup["timezone"]).record_delivery(
                        setup["profile"], coach["topic"]
                    )
        finally:
            store.close()

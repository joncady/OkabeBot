"""Private opt-in morning speech and grounded briefing enrichment."""

import json
import re
from .chores import chore_label
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from .amadeus_coaching import Coaching, SETTINGS, DELIVERY, valid_settings
from .amadeus import encode
from .amadeus_onboarding import KEY, SYSTEM
from .morning import Morning

MORNING_COACHING = {
    "movement": "Would a short stretch feel good before the day gets busy?",
    "rest": "Would you like a quiet moment before getting started?",
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
        self._spoken_chore_refs = []
        self._spoken_chore_scope = []
        self._spoken_chore_slot = None
        self._spoken_chore_profile = None
        self._spoken_chore_delivery = None

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

    def _chores(self):
        from .chores import Chores

        return Chores(
            self.morning.folder, **({"clock": self.morning.clock} if self.morning.clock else {})
        )

    def revalidate_chores(self, spoken):
        """Remove changed/completed private facts immediately before actual speech."""
        if not self._spoken_chore_slot:
            return spoken
        store = self.morning.store()
        try:
            setup = self.morning.preference(store, KEY, {})
            permitted = (
                setup.get("profile") == self._spoken_chore_profile
                and not setup.get("paused")
                and not setup.get("guest")
            )
        finally:
            store.close()
        chores = self._chores()
        current = permitted and all(
            (fresh := chores.still_due(item["id"], item["due_at"], item["revision"]))
            and fresh.get("rooms", []) == item.get("rooms", [])
            for item in self._spoken_chore_scope
        )
        if current:
            return spoken
        spoken = spoken.replace(self._spoken_chore_slot, "", 1)
        self._spoken_chore_refs = []
        self._spoken_chore_scope = []
        self._spoken_chore_slot = None
        return re.sub(r"([.!?])(?:\s*[.!?])+", r"\1", spoken).strip()

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
        due = self._chores().due(limit=3)
        if due:
            cards.append(
                {
                    "kind": "chores",
                    "title": "Around the house",
                    "body": "Ready when you have a moment: "
                    + ", ".join(chore_label(item) for item in due),
                    "important": False,
                }
            )
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
        cards = summary["cards"]
        slots = {"name": name}
        self._spoken_chore_refs = []
        self._spoken_chore_scope = []
        self._spoken_chore_slot = None
        due = self._chores().due(remind_only=True, limit=3)
        if due:
            self._spoken_chore_refs = [
                {k: due[0][k] for k in ("id", "due_at", "revision", "rooms")}
            ]
            self._spoken_chore_scope = [
                {k: item[k] for k in ("id", "due_at", "revision", "rooms")} for item in due
            ]
            title = chore_label(due[0])
            self._spoken_chore_slot = "one household reminder is " + title
            if len(due) > 1:
                self._spoken_chore_slot += ", with more chores listed on the dashboard"
            slots["chores"] = self._spoken_chore_slot
            store = self.morning.store()
            try:
                setup = self.morning.preference(store, KEY, {})
                self._spoken_chore_profile = setup.get("profile")
                self._spoken_chore_delivery = (
                    datetime.fromtimestamp(store.clock(), ZoneInfo(setup.get("timezone", "UTC")))
                    .date()
                    .isoformat()
                )
            finally:
                store.close()
        weather_hint = "unavailable"
        weather = next((c for c in cards if c["kind"] == "weather"), None)
        if weather:
            condition, temperature = weather.get("condition"), weather.get("temperature_c")
            if condition and type(temperature) in (int, float):
                fahrenheit = weather.get("temperature_unit") == "°F"
                degrees = round(temperature * 9 / 5 + 32 if fahrenheit else temperature)
                unit = "Fahrenheit" if fahrenheit else "Celsius"
                description = condition.replace("-", " ").replace("partlycloudy", "partly cloudy")[
                    :32
                ]
                slots["weather"] = (
                    f"it is {description} right now, {degrees} degrees {unit} outside"
                )
                rainy = condition in ("rainy", "pouring", "lightning-rainy")
                cold = temperature <= 15
                weather_hint = "rainy" if rainy else "cool" if cold else "current conditions"
                gear = (["a jacket"] if cold else []) + (["an umbrella"] if rainy else [])
                if gear:
                    slots["advice"] = "if you head out, take " + " and ".join(gear)
            else:
                slots["weather"] = "the weather update is not available yet"
        calendar = [c for c in cards if c["kind"] == "calendar"][:1]
        if calendar:
            values = []
            for card in calendar:
                if card["body"] == "No upcoming timed events in this feed":
                    values.append("your connected calendar has no more timed events listed today")
                elif card.get("spoken"):
                    values.append(
                        card["spoken"].rstrip(".")
                        if len(card["spoken"]) <= 85
                        else "another upcoming event is listed in your connected calendar"
                    )
                else:
                    values.append("your calendar is waiting for a fresh update")
            slots["calendar"] = "; ".join(values)
        important = [c["body"] for c in cards if c.get("important")]
        if important:
            slots["status"] = "; ".join(important)[:160]
        coach = self.coaching()
        if coach:
            slots["coaching"] = coach["body"]

        # Only placeholder names and a coarse weather category reach the model.
        # Event titles, temperatures, person names and notifications remain local slots.
        def fallback():
            return (
                "Good morning, {name}. "
                + ". ".join("{" + k + "}" for k in slots if k != "name")
                + "."
            )

        if len(fallback().format_map(slots)) > 300 and "coaching" in slots:
            del slots["coaching"]
            coach = None
        if len(fallback().format_map(slots)) > 340 and "status" in slots:
            slots["status"] = "there are status updates to check"
        if len(fallback().format_map(slots)) > 360 and "chores" in slots:
            # Keep the important briefing intact rather than failing all speech for
            # an oversized optional chore slot. The persistent card remains due.
            del slots["chores"]
            self._spoken_chore_refs = []
            self._spoken_chore_scope = []
            self._spoken_chore_slot = None
        if len(fallback().format_map(slots)) > 360:
            raise ValueError("Briefing exceeds the short speech budget")
        template, generated = fallback(), False
        if composer:
            try:
                value = composer(character, {"tokens": list(slots), "weather": weather_hint})
                value = " ".join(value.split()).strip('"')
                tokens = re.findall(r"\{([a-z]+)\}", value)
                plain = re.sub(r"\{[a-z]+\}", "", value)
                if (
                    not 8 <= len(value) <= 180
                    or sorted(tokens) != sorted(slots)
                    or "good morning" not in value.casefold()
                    or any(
                        not re.search(r"(?:^|[.!?]\s+)\{" + key + r"\}[.!?](?:\s|$)", value)
                        for key in slots
                        if key != "name"
                    )
                    or re.search(r"[0-9<>{}\[\]`]|https?://", plain)
                ):
                    raise ValueError("Briefing must preserve every grounded slot exactly once")
                if len(value.format_map(slots)) > 360:
                    raise ValueError("Keep the morning briefing short")
                template, generated = value, True
            except InterruptedError:
                raise
            except Exception:
                pass
        return template.format_map(slots), generated, coach

    def complete(self, *, success, coach=None):
        store = self.morning.store()
        try:
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                value = self.morning.preference(store, SPOKEN_KEY, {})
                if value:
                    store.db.execute(
                        "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) "
                        "DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                        (
                            SYSTEM,
                            SPOKEN_KEY,
                            encode(dict(value, state="delivered" if success else "failed")),
                            store.clock(),
                        ),
                    )
                setup = self.morning.preference(store, KEY)
                if success and coach and setup:
                    Coaching(store, timezone=setup["timezone"]).record_delivery(
                        setup["profile"], coach["topic"]
                    )
        finally:
            store.close()
        if (
            success
            and self._spoken_chore_refs
            and setup
            and setup.get("profile") == self._spoken_chore_profile
            and not setup.get("paused")
            and not setup.get("guest")
        ):
            chores = self._chores()
            for item in self._spoken_chore_refs:
                chores.claim_reminder(
                    item["id"],
                    "morning:" + self._spoken_chore_delivery + ":" + item["id"],
                    "morning",
                    expected_due_at=item["due_at"],
                    expected_revision=item["revision"],
                )
        self._spoken_chore_refs = []
        self._spoken_chore_scope = []
        self._spoken_chore_slot = None

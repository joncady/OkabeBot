"""Opt-in, quiet shadow opportunities from observable context and explicit preferences.

No actuator, notification dispatcher or implicit preference inference lives here.
"""

from datetime import datetime, timedelta
import json
import hashlib
from zoneinfo import ZoneInfo

from .amadeus import identifier, encode
from .amadeus_habits import HabitPlanner, CONFIG_KEY, DEFAULTS, preference
from .amadeus_onboarding import SYSTEM, KEY

VERSION = "context-v1"


def configure_context(store, profile, preferences, catalog):
    if not isinstance(profile, str) or not profile or len(profile) > 100:
        raise ValueError("Choose a bounded profile")
    identifier(profile)
    if not isinstance(preferences, dict) or not isinstance(catalog, list) or len(catalog) > 100:
        raise ValueError("Use explicit preferences and a bounded catalogue")
    goals = preferences.get("goals", [])
    if not isinstance(goals, list) or any(
        not isinstance(g, dict)
        or g.get("kind") not in ("morning", "departure", "media")
        or type(g.get("enabled")) is not bool
        for g in goals
    ):
        raise ValueError("Use explicit supported goals")
    media = preferences.get("media", {})
    if not isinstance(media, dict):
        raise ValueError("Use explicit media preferences")
    for key in (
        "genres",
        "avoid",
        "providers",
        "watched_titles",
        "liked_titles",
        "disliked_titles",
    ):
        if not isinstance(media.get(key, []), list) or any(
            not isinstance(v, str) or len(v) > 200 for v in media.get(key, [])
        ):
            raise ValueError("Use bounded media lists")
    if (
        type(media.get("max_minutes", 90)) not in (int, float)
        or not 1 <= media.get("max_minutes", 90) <= 1000
    ):
        raise ValueError("Use a finite media time budget")
    if type(media.get("allow_discovery", False)) is not bool:
        raise ValueError("Discovery requires explicit consent")
    # Validate fully before changing configuration. Catalogue records are independently bounded.
    json.dumps(preferences, allow_nan=False)
    records = []
    for item in catalog:
        if not isinstance(item, dict) or not all(
            k in item for k in ("id", "title", "genres", "minutes", "provider", "content_tags")
        ):
            raise ValueError("Catalogue requires identity, availability, duration and content tags")
        if any(
            not isinstance(item[k], str) or not item[k] or len(item[k]) > 200
            for k in ("title", "provider")
        ):
            raise ValueError("Use bounded title and provider names")
        if type(item["minutes"]) not in (float, int) or not 0 < item["minutes"] <= 1000:
            raise ValueError("Invalid duration")
        if not isinstance(item["id"], str) or len(item["id"]) > 100 or not item["id"]:
            raise ValueError("Invalid catalogue identity")
        for key in ("genres", "content_tags"):
            if not isinstance(item[key], list) or not all(isinstance(v, str) for v in item[key]):
                raise ValueError("Use explicit catalogue tags")
        if len(json.dumps(item)) > 3500:
            raise ValueError("Catalogue item too large")
        records.append(item)
    if len(json.dumps(preferences)) > 4000 or len({r["id"] for r in records}) != len(records):
        raise ValueError("Preferences too large or duplicate catalogue identity")
    values = {
        "context.preferences": preferences,
        "context.catalog": [r["id"] for r in records],
        "context.enabled": True,
    }
    values.update(
        {"context.item." + hashlib.sha256(r["id"].encode()).hexdigest()[:24]: r for r in records}
    )
    encoded = [(profile, k, encode(v), store.clock()) for k, v in values.items()]
    with store.db:
        store.db.execute(
            "CREATE TABLE IF NOT EXISTS context_exposures (subject TEXT NOT NULL, identity TEXT NOT NULL, shown_at REAL NOT NULL, PRIMARY KEY(subject,identity))"
        )
        store.db.execute(
            "DELETE FROM preferences WHERE subject=? AND key LIKE 'context.item.%'", (profile,)
        )
        store.db.executemany(
            "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            encoded,
        )


class ContextPlanner(HabitPlanner):
    def snapshot(self):
        setup = preference(self.store, SYSTEM, KEY)
        if not setup or not preference(self.store, setup["profile"], "context.enabled", False):
            return {"version": VERSION, "state": "disabled", "routines": [], "proposals": []}
        baseline = super().snapshot()
        if baseline["state"] != "shadow":
            return dict(baseline, version=VERSION)
        now = self.store.clock()
        zone = ZoneInfo(setup["timezone"])
        local = datetime.fromtimestamp(now, zone)
        profile = setup["profile"]
        prefs = preference(self.store, profile, "context.preferences", {})
        rows = self.store.db.execute(
            "SELECT id,source,subject,kind,observed_at,payload FROM events WHERE expires_at>? AND observed_at<=? AND subject IN (?,?,?) ORDER BY observed_at,rowid",
            (now, now, profile, "unknown", "household"),
        ).fetchall()
        events = [
            dict(r, payload=json.loads(r["payload"]))
            for r in rows
            if r["source"] in setup["sources"]
        ]
        config = preference(self.store, SYSTEM, CONFIG_KEY, DEFAULTS)
        enabled = {g["kind"] for g in prefs.get("goals", []) if g.get("enabled") is True}
        proposals = []

        def latest(kind):
            return next((e for e in reversed(events) if e["kind"] == kind), None)

        screen = latest("phone_wake")
        avail = {}
        for e in events:
            if e["kind"] == "availability":
                avail[e["payload"]["signal"]] = e
        active_screen = (
            screen and screen["payload"].get("state") == "on" and now - screen["observed_at"] <= 300
        )
        occupied = avail.get("room")
        room = self._room_opening(events, now)
        charging = next(
            (
                e
                for e in reversed(events)
                if e["kind"] == "availability"
                and e["payload"].get("signal") == "charging"
                and e["payload"].get("observation") == "change"
            ),
            None,
        )
        unplug = (
            charging
            and charging["payload"].get("state") == "off"
            and now - charging["observed_at"] <= 900
            and avail.get("charging", {}).get("payload", {}).get("state") == "off"
        )
        context = self._context(events)
        # Screen inactivity is not sleep. Anchor a prepared overview to an
        # observed alarm or the end of sustained DND, then await an opening.
        alarm_cue = next(
            (
                e
                for e in reversed(events)
                if e["kind"] == "phone_alarm"
                and -15 * 60 <= now - e["payload"].get("alarm_at", 0) <= 90 * 60
                and e["observed_at"] <= e["payload"].get("alarm_at", 0) + 900
            ),
            None,
        )
        dnd_start = None
        dnd_cue = None
        for e in events:
            if e["kind"] != "availability" or e["payload"].get("signal") != "dnd":
                continue
            state = e["payload"].get("state")
            if state == "on":
                if dnd_start is None:
                    dnd_start = e["observed_at"]
            else:
                if (
                    state == "off"
                    and e["payload"].get("observation") == "change"
                    and dnd_start is not None
                    and e["observed_at"] - dnd_start >= 3 * 3600
                ):
                    dnd_cue = e
                dnd_start = None
        first_wake = alarm_cue is not None or (
            dnd_cue and 0 <= now - dnd_cue["observed_at"] <= 5400
        )
        if (
            "morning" in enabled
            and (active_screen or room)
            and first_wake
            and ("weather" in context or "upcoming" in context)
        ):
            proposals.append(
                self._proposal(
                    "wake",
                    self._brief(context, zone, whole_day=True),
                    screen if active_screen else occupied,
                    context,
                    local,
                )
            )
        # Departure timing is evidence, not a scheduled interruption. Require an actual unplug cue.
        departure = next((r for r in baseline["routines"] if r["kind"] == "departure"), None)
        minute = local.hour * 60 + local.minute
        if (
            "departure" in enabled
            and unplug
            and departure
            and abs(minute - departure["minute"]) <= 60
            and context
        ):
            proposals.append(
                self._proposal(
                    "departure",
                    "Before you head out: " + self._brief(context, zone),
                    charging,
                    context,
                    local,
                )
            )
        # A quiet opening is not permission to autoplay. Only show choices; no claim of free time.
        media_routine = next((r for r in baseline["routines"] if r["kind"] == "media"), None)
        media_window = (
            media_routine and media_routine["minute"] - 90 <= minute <= media_routine["minute"]
        )
        discovery = prefs.get("media", {}).get("allow_discovery") is True
        already_played = any(
            e["observed_at"] >= local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            and (
                (e["kind"] == "media" and e["payload"].get("state") in ("PLAYING", "BUFFERING"))
                or (
                    e["kind"] == "tv_state"
                    and e["payload"].get("state", "").lower() in ("playing", "buffering")
                )
            )
            for e in events
        )
        if (
            "media" in enabled
            and not already_played
            and (media_window or discovery)
            and (active_screen or room)
        ):
            choices = self._choices(profile, prefs, context, now)
            if choices:
                text = (
                    "If you feel like watching: "
                    + " or ".join(
                        f"{c['title']} ({c['minutes']} min, {c['provider']})" for c in choices
                    )
                    + ". From your saved catalogue; availability may vary."
                )
                p = self._proposal(
                    "media",
                    text,
                    screen if active_screen else occupied,
                    dict(context, choices=choices),
                    local,
                )
                proposals.append(p)
        # Feed-derived opportunities are shadow-only and use the same attention
        # gates. Enabling collection is not permission to dispatch these proposals.
        from .amadeus_feeds import context as feed_context

        source_context = feed_context(self.store, full=True)
        cue = screen if active_screen else occupied if room else None
        if cue:
            for feed in source_context:
                useful = []
                if feed["source"] == "transit":
                    useful = [
                        i["title"]
                        for i in feed["items"]
                        if i.get("effect")
                        in ("NO_SERVICE", "REDUCED_SERVICE", "SIGNIFICANT_DELAYS", "DETOUR")
                    ]
                elif feed["source"] == "appliances":
                    useful = [
                        i["label"] + ": " + i["state"]
                        for i in feed["items"]
                        if i.get("state", "").casefold()
                        in ("complete", "completed", "finished", "error")
                    ]
                elif feed["source"] == "tasks":
                    for item in feed["items"]:
                        if item.get("state") != "needs_action" or not item.get("due"):
                            continue
                        try:
                            due = datetime.fromisoformat(item["due"].replace("Z", "+00:00"))
                            if due.tzinfo is None:
                                due = due.replace(tzinfo=zone)
                            if now <= due.timestamp() <= now + 86400:
                                useful.append(item["title"] + " · due " + item["due"])
                        except ValueError:
                            continue
                if useful:
                    proposals.append(
                        self._proposal(
                            feed["source"],
                            "; ".join(useful[:2]),
                            cue,
                            {"source": feed["source"], "complete": feed["complete"]},
                            local,
                        )
                    )
        for p in proposals:
            reason = self._gate(setup, config, events, p["kind"], local)
            if reason is None:
                reason = self._attention_gate(events, setup, now)
            p.update(eligible=reason is None, reason=reason or "eligible")
        # One useful card at a time. Morning/departure outrank entertainment.
        found = False
        for p in proposals:
            if p["eligible"]:
                if found:
                    p.update(eligible=False, reason="higher_priority_opportunity")
                found = True
        return {
            "version": VERSION,
            "state": "shadow",
            "routines": baseline["routines"],
            "proposals": proposals,
        }

    def _context(self, events):
        context = super()._context(events)
        now = self.store.clock()
        setup = preference(self.store, SYSTEM, KEY)
        zone = ZoneInfo(setup["timezone"])
        local = datetime.fromtimestamp(now, zone)
        tomorrow = (
            (local + timedelta(days=1))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        marker = next((e for e in reversed(events) if e["kind"] == "calendar_snapshot"), None)
        if marker and now - marker["observed_at"] <= 600:
            context["day_agenda"] = sorted(
                (
                    {"summary": e["payload"]["summary"], "start_at": e["payload"]["start_at"]}
                    for e in events
                    if e["kind"] == "calendar"
                    and e["payload"].get("snapshot_id") == marker["payload"]["snapshot_id"]
                    and e["payload"].get("all_day") != "yes"
                    and now < e["payload"]["start_at"] < tomorrow
                ),
                key=lambda p: p["start_at"],
            )[:3]
        return context

    def _proposal(self, kind, text, cue, context, local):
        return {
            "kind": kind,
            "text": text,
            "context": context,
            "shadow": True,
            "action": "quiet_card",
            "expires_at": self.store.clock() + 900,
            "proposal_id": f"{VERSION}:{local.date().isoformat()}:{kind}:{cue['id']}",
            "routine": {"kind": kind, "version": VERSION, "cue_id": cue["id"]},
        }

    def _attention_gate(self, events, setup, now):
        if "availability" not in setup["sources"]:
            return "availability_not_consented"
        signals = {}
        media = {}
        television = {}
        for e in events:
            if e["kind"] == "availability":
                signals[(e["payload"]["signal"], e["payload"].get("device_id", "default"))] = e
            if e["kind"] == "tv_state":
                television[e["payload"].get("device_id", "")] = e
            if e["kind"] == "media":
                media[e["payload"].get("device_id", e["payload"].get("app", ""))] = e
        respect_dnd = preference(
            self.store, setup["profile"], "conversation.interruptions", {}
        ).get("respect_dnd", True)
        for signal in ("dnd", "focus") if respect_dnd else ("focus",):
            devices = [e for (name, _), e in signals.items() if name == signal]
            if not devices or any(
                now - e["observed_at"] > 600 or e["payload"].get("state") != "off" for e in devices
            ):
                return signal + "_active_or_unknown"
        if any(e["payload"].get("state") not in ("IDLE", "OFF", "STOPPED") for e in media.values()):
            return "media_attention"
        if any(
            e["payload"].get("state", "").lower() not in ("idle", "off", "standby")
            for e in television.values()
        ):
            return "tv_attention"
        marker = next((e for e in reversed(events) if e["kind"] == "calendar_snapshot"), None)
        if "calendar" in setup["sources"]:
            if not marker or now - marker["observed_at"] > 600:
                return "calendar_stale"
            if marker["payload"].get("busy_coverage") != "complete":
                return "calendar_busy_coverage_unknown"
            for e in events:
                p = e["payload"]
                if (
                    e["kind"] == "calendar"
                    and p.get("snapshot_id") == marker["payload"]["snapshot_id"]
                    and p.get("busy") == "busy"
                    and p["start_at"] - 600 <= now < p.get("end_at", p["start_at"] + 3600)
                ):
                    return "calendar_busy"
        return None

    def _acknowledge(self, proposal):
        # Only authoritative, currently eligible choices count as shown. A view or
        # forged payload must not silently alter taste or viewing history.
        match = next(
            (
                p
                for p in self.snapshot()["proposals"]
                if p["proposal_id"] == proposal.get("proposal_id") and p["eligible"]
            ),
            None,
        )
        if match is None:
            raise ValueError("Proposal is no longer eligible")
        super()._acknowledge(proposal)
        profile = preference(self.store, SYSTEM, KEY)["profile"]
        now = self.store.clock()
        self.store.db.execute(
            "DELETE FROM context_exposures WHERE subject=? AND shown_at<?",
            (profile, now - 7 * 86400),
        )
        for choice in match["context"].get("choices", []):
            self.store.db.execute(
                "INSERT INTO context_exposures VALUES (?,?,?) ON CONFLICT(subject,identity) DO UPDATE SET shown_at=excluded.shown_at",
                (profile, choice["id"], now),
            )

    def _room_opening(self, events, now):
        room = next(
            (
                e
                for e in reversed(events)
                if e["kind"] == "availability" and e["payload"].get("signal") == "room"
            ),
            None,
        )
        if not room or room["payload"].get("state") != "on" or now - room["observed_at"] > 600:
            return False
        change = next(
            (
                e
                for e in reversed(events)
                if e["kind"] == "availability"
                and e["payload"].get("signal") == "room"
                and e["payload"].get("device_id", "default")
                == room["payload"].get("device_id", "default")
                and e["payload"].get("observation") == "change"
            ),
            None,
        )
        return bool(
            change and change["payload"].get("state") == "on" and now - change["observed_at"] <= 900
        )

    def _gate(self, setup, config, events, kind, local):
        # Base policy includes consent, quiet, correction, dedupe and shared attention budget.
        reason = super()._gate(setup, config, events, kind, local)
        # Rich interval check replaces the old blanket ±30-minute calendar block.
        if (
            reason == "availability_unknown"
            and kind == "wake"
            and self._room_opening(events, self.store.clock())
        ):
            reason = None
        return None if reason == "calendar_nearby" else reason

    def _brief(self, context, zone, *, whole_day=False):
        parts = []
        weather = context.get("weather")
        if weather:
            condition = {
                "partlycloudy": "partly cloudy",
                "lightning-rainy": "thunderstorms and rain",
                "clear-night": "clear",
                "snowy-rainy": "snow and rain",
            }.get(weather["condition"], weather["condition"].replace("-", " ").replace("_", " "))
            parts.append(f"{weather['temperature_c']:g}°C and {condition}.")
            gear = context.get("outdoor_gear", [])
            if gear:
                parts.append(
                    "Consider "
                    + " and ".join("an umbrella" if g == "umbrella" else "a jacket" for g in gear)
                    + " if you go outside."
                )
        else:
            parts.append("Current weather is unavailable.")
        upcoming = context.get("day_agenda" if whole_day else "upcoming")
        if upcoming:
            parts.append(
                "Next on your calendar: "
                + "; ".join(
                    p["summary"]
                    + " at "
                    + datetime.fromtimestamp(p["start_at"], zone).strftime("%H:%M")
                    for p in upcoming
                )
                + "."
            )
        elif "calendar_checked_at" in context:
            parts.append(
                (
                    "No more timed entries today on this feed; other plans may be missing."
                    if whole_day
                    else "No timed entries in the next four hours on this feed; other plans may be missing."
                )
            )
        else:
            parts.append("Calendar information is unavailable.")
        return " ".join(parts)

    def _choices(self, profile, preferences, context, now):
        prefs = preferences.get("media", {})
        maximum = prefs.get("max_minutes", 90)
        upcoming = context.get("upcoming", [])
        if upcoming:
            maximum = min(maximum, max(0, (upcoming[0]["start_at"] - now) / 60 - 15))
        genres = {g.casefold() for g in prefs.get("genres", [])}
        avoids = {g.casefold() for g in prefs.get("avoid", [])}
        watched = set(prefs.get("watched_titles", [])) | set(prefs.get("disliked_titles", []))
        from .amadeus_feeds import context as feed_context

        for feed in feed_context(self.store, full=True):
            if feed["source"] == "watch_history":
                watched.update(i["title"] for i in feed["items"] if i.get("type") == "movie")
        exposed = {
            row[0]
            for row in self.store.db.execute(
                "SELECT identity FROM context_exposures WHERE subject=? AND shown_at>?",
                (profile, now - 7 * 86400),
            )
        }
        matches = []
        for identity in preference(self.store, profile, "context.catalog", []):
            item = preference(
                self.store,
                profile,
                "context.item." + hashlib.sha256(identity.encode()).hexdigest()[:24],
            )
            if (
                not item
                or identity in exposed
                or item["title"] in watched
                or item["provider"] not in prefs.get("providers", [])
                or item["minutes"] > maximum
            ):
                continue
            tags = {s.casefold() for s in item["content_tags"] + item["genres"]}
            if tags & avoids or not tags & genres:
                continue
            matches.append(item)
        return sorted(
            matches,
            key=lambda i: (
                -len(set(g.casefold() for g in i["genres"]) & genres),
                i["minutes"],
                i["id"],
            ),
        )[:2]

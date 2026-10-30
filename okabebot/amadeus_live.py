"""Opt-in door-armed conversation trial. No ambient recording or speaker discovery."""

from contextlib import closing
import json
import math
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .amadeus import Store, encode
from .amadeus_habits import preference
from .amadeus_onboarding import KEY, SYSTEM
from .amadeus_conversation import PreferenceConversation, FIELDS

CONFIG = "conversation.live"
STATE = "conversation.trial"
BUDGET = "conversation.invitation_budget"
FREQUENCY_DEFAULTS = {"max_per_day": 1, "min_gap_minutes": 120}


def confirmation_answer(text):
    """Acknowledge the pending meaning, never arbitrary content after a yes.

    Corrections, conditions, uncertainty and questions require a new clarification.
    Only the existing pending proposal may be saved from an affirmative response.
    """
    value = " ".join(text.casefold().replace("’", "'").split())
    if value.endswith("?"):
        return None
    if re.search(
        r"\b(but|except|instead|actually|rather|maybe|perhaps|unless|wait|however|only|if|not|never|don't|do not)\b",
        value,
    ):
        if value.rstrip(".! ") in ("don't remember that", "do not remember that"):
            return False
        return None
    if re.match(r"^(?:yes|yeah|yep|sure|absolutely|please do|remember that)\b", value):
        if re.search(r"\b(no|nope|nah)\b", value):
            return None
        return True
    if value.rstrip(".! ") in ("no", "no thanks", "nope", "nah", "just tonight"):
        return False
    return None


class ProactiveConversation:
    def __init__(self, folder, clock=time.time, presence_provider=None, state_key=STATE):
        self.folder, self.clock = Path(folder), clock
        self.state_key = state_key
        self.turn_limit = 6
        self.lock = threading.RLock()
        self.clear_since = None
        self.presence_provider = presence_provider

    def store(self):
        return closing(Store(self.folder, clock=self.clock))

    def interruptions(self, data=None):
        """Owner policy only: never changes the phone's actual DND setting."""
        if data is not None and (
            set(data) != {"respect_dnd"} or type(data["respect_dnd"]) is not bool
        ):
            raise ValueError("Choose whether Amadeus respects phone DND")
        with self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            if not setup.get("profile"):
                if data is None:
                    return {"respect_dnd": True}
                raise ValueError("Save private setup first")
            value = {
                "respect_dnd": True,
                **preference(s, setup["profile"], "conversation.interruptions", {}),
            }
            if data is not None:
                value.update(data)
                s.remember(setup["profile"], "conversation.interruptions", value)
                self.clear_since = None
            return value

    def configure(self, *, enabled, destination, max_per_day=None, min_gap_minutes=None):
        if (
            type(enabled) is not bool
            or not isinstance(destination, str)
            or not 1 <= len(destination) <= 100
        ):
            raise ValueError("Choose an enabled flag and registered destination")
        for key, value, low, high in (
            ("max_per_day", max_per_day, 1, 6),
            ("min_gap_minutes", min_gap_minutes, 30, 720),
        ):
            if value is not None and (type(value) is not int or not low <= value <= high):
                raise ValueError("Choose a bounded proactive frequency")
        with self.lock, self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = preference(store, SYSTEM, KEY, {})
            if not setup or "door_presence" not in setup.get("sources", []):
                raise ValueError("Door observation consent required")
            profile = setup["profile"]
            old = preference(store, profile, CONFIG, {})
            settings = {**FREQUENCY_DEFAULTS, **old}
            changed = (
                not old or old.get("enabled") != enabled or old.get("destination") != destination
            )
            settings.update(enabled=enabled, destination=destination)
            if changed:
                settings["activated_at"] = self.clock()
            if max_per_day is not None:
                settings["max_per_day"] = max_per_day
            if min_gap_minutes is not None:
                settings["min_gap_minutes"] = min_gap_minutes
            state = preference(store, profile, self.state_key, {})
            day = self._day(setup)
            budget = self._budget(store, profile, state, day)
            records = [
                (profile, CONFIG, encode(settings), self.clock()),
                (profile, BUDGET, encode(budget), self.clock()),
            ]
            if changed:
                records.append((profile, self.state_key, encode({}), self.clock()))
            # Frequency and destination edits do not override private memory/speech
            # choices. The explicit enable switch retains its previous opt-in role.
            if not old or old.get("enabled") != enabled:
                prefs = preference(store, profile, "conversation.preferences", {})
                records.append(
                    (
                        profile,
                        "conversation.preferences",
                        encode(dict(prefs, enabled=enabled, speech=enabled)),
                        self.clock(),
                    )
                )
            store.db.executemany(
                "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) "
                "DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                records,
            )
            return settings

    def _day(self, setup):
        return (
            datetime.fromtimestamp(self.clock(), ZoneInfo(setup.get("timezone", "UTC")))
            .date()
            .isoformat()
        )

    def _budget(self, store, profile, state, day):
        saved = preference(store, profile, BUDGET, {})
        count, last = 0, None
        if saved:
            count = saved.get("count")
            last = saved.get("last_attempt_at")
            if (
                type(count) is not int
                or count < 0
                or (
                    last is not None and (type(last) not in (int, float) or not math.isfinite(last))
                )
            ):
                return {"day": day, "count": 6, "last_attempt_at": self.clock()}
            count = count if saved.get("day") == day else 0
        # Reconcile known legacy consumption even if a pre-migration zero ledger
        # exists. Reading a real invitation must never grant a fresh daily budget.
        delivered = preference(store, profile, "conversation.chore_delivery", {})
        consumed = (
            state.get("consumed") is True and state.get("day") == day or delivered.get("day") == day
        )
        if consumed and count == 0:
            candidates = [
                last,
                state.get("claimed_at"),
                preference(store, profile, "conversation.chore_attempt", {}).get("at"),
            ]
            if state.get("session_until", 0) > 600:
                candidates.append(state["session_until"] - 600)
            known = [
                value
                for value in candidates
                if type(value) in (int, float)
                and math.isfinite(value)
                and 0 <= value <= self.clock()
            ]
            count, last = 1, max(known) if known else self.clock()
        return {"day": day, "count": count, "last_attempt_at": last}

    def _migrate_budget(self, store, profile, setup, cfg, state, day, budget):
        saved = preference(store, profile, BUDGET, {})
        prior_count = saved.get("count", 0) if saved.get("day") == day else 0
        if type(prior_count) is not int:
            prior_count = 6
        if not budget["count"] or prior_count >= budget["count"]:
            return budget
        with store.db:
            store.db.execute("BEGIN IMMEDIATE")
            if (
                preference(store, SYSTEM, KEY, {}) != setup
                or preference(store, profile, CONFIG, {}) != cfg
                or preference(store, profile, self.state_key, {}) != state
            ):
                return None
            current = self._budget(store, profile, state, day)
            store.db.execute(
                "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) "
                "DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (profile, BUDGET, encode(current), self.clock()),
            )
            return current

    def _budget_allowed(self, cfg, budget):
        maximum = cfg.get("max_per_day", FREQUENCY_DEFAULTS["max_per_day"])
        gap = cfg.get("min_gap_minutes", FREQUENCY_DEFAULTS["min_gap_minutes"])
        if (
            type(maximum) is not int
            or not 1 <= maximum <= 6
            or type(gap) is not int
            or not 30 <= gap <= 720
        ):
            return False
        last = budget.get("last_attempt_at")
        return budget["count"] < maximum and (last is None or self.clock() - last >= gap * 60)

    @staticmethod
    def _home_confirmed(attention, home):
        if home.get("configured"):
            return bool(
                home.get("fresh")
                and home.get("healthy_scanners") == 2
                and home.get("presence") == "home"
            )
        return attention.get("presence") == "home"

    def _checkin_offer(self, profile, cfg, state, day, attention, home):
        if (
            cfg.get("max_per_day", 1) <= 1
            or state.get("session_until", 0) > self.clock()
            or not self._home_confirmed(attention, home)
        ):
            return None
        return {
            "kind": "checkin",
            "profile": profile,
            "destination": cfg.get("destination"),
            "day": day,
        }

    def enabled(self):
        with self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            return preference(s, setup.get("profile", SYSTEM), CONFIG, {}).get("enabled") is True

    def door(self, data):
        with self.lock, self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            profile = setup.get("profile", SYSTEM)
            cfg = preference(s, profile, CONFIG, {})
            if not self.permitted(setup, cfg):
                return False
            bindings = json.loads((self.folder / "ha-bindings.json").read_text())
            stamp = data.get("observed_at")
            if (
                data.get("entity_id") not in bindings.get("door", [])
                or data.get("state") != "on"
                or str(data.get("event_id", "")).startswith("snapshot:")
                or type(stamp) not in (int, float)
                or not 0 <= self.clock() - stamp <= 60
                or stamp < cfg["activated_at"]
            ):
                return False
            day = datetime.fromtimestamp(stamp, ZoneInfo(setup["timezone"])).date().isoformat()
            state = preference(s, profile, self.state_key, {})
            if state.get("day") == day:
                return False
            s.remember(
                profile,
                self.state_key,
                dict(
                    day=day,
                    armed_at=stamp,
                    ready_after=stamp + 180 + secrets.randbelow(720),
                    expires_at=stamp + 6 * 3600,
                    consumed=False,
                    session_until=0,
                ),
            )
            self.clear_since = None
            return True

    @staticmethod
    def permitted(setup, cfg):
        return (
            cfg.get("enabled") is True
            and setup.get("paused") is False
            and setup.get("guest") is False
            and "door_presence" in setup.get("sources", [])
        )

    def attention(self, data):
        """Overwrite bounded current gate state; no history, titles or room inference."""
        if not isinstance(data, dict) or set(data) != {
            "observed_at",
            "dnd",
            "dnd_reported_at",
            "focus",
            "media",
            "presence",
        }:
            raise ValueError("Invalid attention snapshot")
        now = self.clock()
        if any(
            type(data[k]) not in (int, float) or not math.isfinite(data[k])
            for k in ("observed_at", "dnd_reported_at")
        ):
            raise ValueError("Invalid attention timestamps")
        if not 0 <= now - data["observed_at"] <= 60:
            raise ValueError("Attention snapshot is stale")
        if not 0 <= data["dnd_reported_at"] <= now:
            raise ValueError("Invalid phone report timestamp")
        if data["dnd"] not in ("on", "off", "unknown") or data["focus"] not in (
            "on",
            "off",
            "unknown",
        ):
            raise ValueError("Invalid DND/focus state")
        if data["media"] not in ("clear", "occupied", "unknown") or data["presence"] not in (
            "home",
            "away",
            "unknown",
        ):
            raise ValueError("Invalid household state")
        # A current publisher snapshot and an expired phone report are different
        # facts. Preserve current media/focus evidence; stale DND still blocks speech.
        data = dict(data)
        if now - data["dnd_reported_at"] > 1800:
            data["dnd"] = "unknown"
        with self.lock, self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            profile = setup.get("profile", SYSTEM)
            if self.permitted(setup, preference(s, profile, CONFIG, {})):
                s.remember(profile, "conversation.attention", data)

    def _chores(self):
        from .chores import Chores

        return Chores(self.folder, clock=self.clock)

    def _chore_offer(self, s, profile, cfg, state, day):
        if state.get("session_until", 0) > self.clock():
            return None
        due = self._chores().due_from_store(s, remind_only=True, limit=3)
        if not due:
            return None
        return {
            "kind": "chores",
            "profile": profile,
            "destination": cfg.get("destination"),
            "day": day,
            "chores": [
                {key: item[key] for key in ("id", "title", "due_at", "revision", "rooms")}
                for item in due
            ],
        }

    def _household_offer(self, store, profile, cfg, state, day, *, update=False):
        from .household_nudges import HouseholdNudges

        home = self.presence_provider() if self.presence_provider else {}
        item = HouseholdNudges(store, home).offer(update=update)
        if item is None or state.get("session_until", 0) > self.clock():
            return None
        return dict(
            kind="household",
            profile=profile,
            destination=cfg.get("destination"),
            day=day,
            household=item,
        )

    def _health_offer(self, store, profile, cfg, state, day):
        from .amadeus_health import Health

        if state.get("session_until", 0) > self.clock():
            return None
        item = Health(store).offer()
        return (
            dict(
                kind="health",
                profile=profile,
                destination=cfg.get("destination"),
                day=day,
                health=item,
            )
            if item
            else None
        )

    @staticmethod
    def chore_text(items):
        from .chores import chore_label

        titles = [chore_label(item) for item in items[:3]]
        return "these chores are ready when you have a moment: " + ", ".join(titles)

    def opening(self, offer, composer):
        """Generate framing only. Chore titles remain local, untrusted data slots."""
        if offer.get("kind") == "health":
            return {"reply": offer["health"]["text"], "memory": None}
        if offer.get("kind") == "household":
            fragment = offer["household"]["text"]
            template = "A household note: {household}"
            try:
                result = composer(
                    "Frame one optional household note in character. Use the exact placeholder {household} once. Do not invent facts, people, actions, urgency or health advice; no memory proposal. Keep the framing brief and non-judgmental.",
                    {
                        "preferences": {},
                        "capabilities": ["Framing only; no actions or memory writes"],
                    },
                )
                value = result.get("reply") if isinstance(result, dict) else None
                if (
                    not isinstance(value, str)
                    or result.get("memory") is not None
                    or value.count("{household}") != 1
                    or any(c in value.replace("{household}", "") for c in "{}<>")
                    or len(value.replace("{household}", fragment)) > 300
                    or re.search(
                        r"\b(lazy|shame|failure|you never|must do|should have)\b", value, re.I
                    )
                ):
                    raise ValueError("Invalid household framing")
                template = value
            except InterruptedError:
                raise
            except Exception:
                pass
            return {"reply": template.replace("{household}", fragment), "memory": None}
        if offer.get("kind") != "chores":
            with self.store() as s:
                setup = preference(s, SYSTEM, KEY, {})
                prefs = preference(s, setup.get("profile", SYSTEM), "context.preferences", {})
            return composer(
                "Start one optional conversation about an interest or hobby. I can answer with the button or skip it.",
                {"preferences": prefs},
            )
        fragment = self.chore_text(offer.get("chores", []))
        template = "A little household note: {chores}. You can scan the tag when done, or leave it for later."
        try:
            result = composer(
                "Offer one gentle optional chore reminder in character. Use the exact placeholder {chores} once, and no other placeholders. Framing only: do not invent chores, dates, completion, user behavior or urgency. Never shame, pressure or guilt. Do not propose memory. Mention the tag or dashboard only as a way to mark completion.",
                {"preferences": {}, "capabilities": ["Framing only; no tools or memory changes"]},
            )
            value = result.get("reply") if isinstance(result, dict) else None
            if (
                not isinstance(value, str)
                or not 1 <= len(value) <= 180
                or result.get("memory") is not None
                or value.count("{chores}") != 1
                or "{" in value.replace("{chores}", "")
                or "}" in value.replace("{chores}", "")
                or "<" in value
                or re.search(r"\b(lazy|shame|failure|you never|must do|should have)\b", value, re.I)
                or len(value.replace("{chores}", fragment)) > 300
            ):
                raise ValueError("Invalid gentle chore framing")
            template = value
        except InterruptedError:
            raise
        except Exception:
            pass
        return {"reply": template.replace("{chores}", fragment), "memory": None}

    def revalidate_chore_offer(self, offer):
        """Last factual/privacy gate after capture shutdown, before actual output."""
        if offer.get("kind") == "health":
            with self.store() as s:
                setup = preference(s, SYSTEM, KEY, {})
                profile = setup.get("profile", SYSTEM)
                cfg = preference(s, profile, CONFIG, {})
                state = {**preference(s, profile, self.state_key, {}), "session_until": 0}
                return (
                    self.permitted(setup, cfg)
                    and self._health_offer(s, profile, cfg, state, self._day(setup)) == offer
                )
        if offer.get("kind") == "household":
            with self.store() as s:
                setup = preference(s, SYSTEM, KEY, {})
                profile = setup.get("profile", SYSTEM)
                cfg = preference(s, profile, CONFIG, {})
                state = preference(s, profile, self.state_key, {})
                # A claimed household session is active; ignore it for factual revalidation.
                state = {**state, "session_until": 0}
                return bool(
                    profile == offer.get("profile")
                    and self.permitted(setup, cfg)
                    and self._household_offer(s, profile, cfg, state, self._day(setup)) == offer
                )
        if offer.get("kind") != "chores":
            return True
        with self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            profile = setup.get("profile", SYSTEM)
            cfg = preference(s, profile, CONFIG, {})
            if (
                profile != offer.get("profile")
                or not self.permitted(setup, cfg)
                or cfg.get("destination") != offer.get("destination")
            ):
                return False
            from .chores import MAX_CHORES

            eligible = {
                item["id"]: item
                for item in self._chores().due_from_store(s, remind_only=True, limit=MAX_CHORES)
            }
            valid = bool(offer.get("chores")) and all(
                item["id"] in eligible
                and all(
                    eligible[item["id"]][key] == item[key]
                    for key in ("due_at", "revision", "rooms")
                )
                for item in offer["chores"]
            )
            return (
                valid
                and preference(s, SYSTEM, KEY, {}) == setup
                and preference(s, profile, CONFIG, {}) == cfg
            )

    def delivered(self, offer, *, success):
        """Acknowledge only actual speech; failed attempts retain future reminders."""
        if offer.get("kind") == "health" and success:
            from .amadeus_coaching import Coaching

            if self.revalidate_chore_offer(offer):
                with self.store() as s:
                    setup = preference(s, SYSTEM, KEY, {})
                    Coaching(s, timezone=setup["timezone"]).record_delivery(
                        setup["profile"], offer["health"]["topic"]
                    )
            return
        if offer.get("kind") == "household" and success:
            from .household_nudges import HouseholdNudges

            with self.store() as s, s.db:
                s.db.execute("BEGIN IMMEDIATE")
                setup = preference(s, SYSTEM, KEY, {})
                profile = setup.get("profile", SYSTEM)
                trial = preference(s, profile, self.state_key, {})
                if (
                    profile == offer.get("profile")
                    and trial.get("invitation_kind") == "household"
                    and trial.get("session_until", 0) > self.clock()
                    and trial.get("consumed") is True
                    and trial.get("day") == offer.get("day")
                ):
                    home = self.presence_provider() if self.presence_provider else {}
                    HouseholdNudges(s, home).delivered(offer["household"])
            return
        if offer.get("kind") != "chores" or not success:
            return
        with self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            trial = preference(s, setup.get("profile", SYSTEM), self.state_key, {})
            if (
                setup.get("profile") != offer.get("profile")
                or setup.get("paused")
                or setup.get("guest")
                or trial.get("invitation_kind") != "chores"
                or trial.get("consumed") is not True
                or trial.get("day") != offer.get("day")
                or trial.get("session_until", 0) <= self.clock()
            ):
                return
        delivered = False
        chores = self._chores()
        for item in offer.get("chores", []):
            delivered = (
                chores.claim_reminder(
                    item["id"],
                    "proactive:" + str(offer["day"]) + ":" + item["id"],
                    "proactive",
                    expected_due_at=item["due_at"],
                    expected_revision=item["revision"],
                )
                or delivered
            )
        if delivered:
            with self.store() as s, s.db:
                s.db.execute("BEGIN IMMEDIATE")
                setup = preference(s, SYSTEM, KEY, {})
                trial = preference(s, setup.get("profile", SYSTEM), self.state_key, {})
                if (
                    setup.get("profile") == offer.get("profile")
                    and not setup.get("paused")
                    and not setup.get("guest")
                    and trial.get("invitation_kind") == "chores"
                    and trial.get("consumed") is True
                    and trial.get("day") == offer.get("day")
                ):
                    s.remember(
                        setup["profile"], "conversation.chore_delivery", {"day": offer["day"]}
                    )

    def check(self, *, destination, busy, focus, media, quiet, audio_ready):
        with self.lock, self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            profile = setup.get("profile", SYSTEM)
            cfg = preference(s, profile, CONFIG, {})
            state = preference(s, profile, self.state_key, {})
            a = preference(s, profile, "conversation.attention", {})
            now = self.clock()
            local = datetime.fromtimestamp(now, ZoneInfo(setup.get("timezone", "UTC"))).strftime(
                "%H:%M"
            )
            start, end = setup.get("quiet_start", "00:00"), setup.get("quiet_end", "00:00")
            asleep = start <= local < end if start < end else local >= start or local < end
            calendar_busy = False
            if "calendar" in setup.get("sources", []):
                marker = s.db.execute(
                    "SELECT payload,observed_at FROM events WHERE kind='calendar_snapshot' AND subject=? ORDER BY observed_at DESC,rowid DESC LIMIT 1",
                    (profile,),
                ).fetchone()
                calendar_busy = not marker or now - marker["observed_at"] > 600
                if marker and not calendar_busy:
                    snapshot = json.loads(marker["payload"])
                    calendar_busy = snapshot.get("busy_coverage") != "complete"
                    for row in s.db.execute(
                        "SELECT payload FROM events WHERE kind='calendar' AND subject=? AND expires_at>?",
                        (profile, now),
                    ):
                        event = json.loads(row["payload"])
                        if (
                            event.get("snapshot_id") == snapshot.get("snapshot_id")
                            and event.get("busy") == "busy"
                            and event["start_at"] - 600
                            <= now
                            < event.get("end_at", event["start_at"] + 3600)
                        ):
                            calendar_busy = True
            respect_dnd = preference(s, profile, "conversation.interruptions", {}).get(
                "respect_dnd", True
            )
            home = self.presence_provider() if self.presence_provider else {}
            presence_blocked = home.get("configured") and (
                not home.get("fresh")
                or home.get("healthy_scanners") != 2
                or home.get("presence") != "home"
            )
            day = (
                datetime.fromtimestamp(now, ZoneInfo(setup.get("timezone", "UTC")))
                .date()
                .isoformat()
            )
            budget = self._budget(s, profile, state, day)
            if self.permitted(setup, cfg):
                budget = self._migrate_budget(s, profile, setup, cfg, state, day, budget)
                if budget is None:
                    self.clear_since = None
                    return None
            checkin_offer = self._checkin_offer(profile, cfg, state, day, a, home)
            chore_offer = (
                self._chore_offer(s, profile, cfg, state, day)
                if self.permitted(setup, cfg)
                else None
            )
            household_offer = (
                self._household_offer(s, profile, cfg, state, day, update=True)
                if self.permitted(setup, cfg)
                else None
            )
            health_offer = (
                self._health_offer(s, profile, cfg, state, day)
                if self.permitted(setup, cfg)
                else None
            )
            door_ready = bool(
                state
                and state.get("consumed") is False
                and now < state.get("expires_at", 0)
                and now >= state.get("ready_after", now + 1)
            )
            from .amadeus_feeds import room_media_busy

            blocked = (
                presence_blocked
                or not self.permitted(setup, cfg)
                or not self._budget_allowed(cfg, budget)
                or not (
                    chore_offer or household_offer or health_offer or door_ready or checkin_offer
                )
                or destination != cfg.get("destination")
                or busy
                or calendar_busy
                or focus
                or media
                or room_media_busy(s)
                or quiet
                or asleep
                or not audio_ready
                or now - a.get("observed_at", 0) > 150
                or (
                    respect_dnd
                    and (now - a.get("dnd_reported_at", 0) > 1800 or a.get("dnd") != "off")
                )
                or a.get("focus") != "off"
                or a.get("media") != "clear"
                or (not home.get("configured") and a.get("presence") == "away")
            )
            if blocked:
                self.clear_since = None
                return None
            if self.clear_since is None:
                self.clear_since = now
            if now - self.clear_since < 120:
                return None
            return (
                chore_offer
                or household_offer
                or health_offer
                or (
                    dict(destination=cfg["destination"], day=state["day"])
                    if door_ready
                    else checkin_offer
                )
            )

    def claim(self, offer):
        # Caller rechecks attention and output route immediately before claiming.
        with self.lock, self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = preference(store, SYSTEM, KEY, {})
            profile = setup.get("profile", SYSTEM)
            state = preference(store, profile, self.state_key, {})
            cfg = preference(store, profile, CONFIG, {})
            day = self._day(setup)
            budget = self._budget(store, profile, state, day)
            if not self.permitted(setup, cfg) or not self._budget_allowed(cfg, budget):
                return False
            kind = offer.get("kind")
            if kind == "health":
                if self._health_offer(store, profile, cfg, state, day) != offer:
                    return False
            elif kind == "household":
                if self._household_offer(store, profile, cfg, state, day) != offer:
                    return False
            elif kind == "chores":
                if self._chore_offer(store, profile, cfg, state, day) != offer:
                    return False
            elif kind == "checkin":
                attention = preference(store, profile, "conversation.attention", {})
                home = self.presence_provider() if self.presence_provider else {}
                if self._checkin_offer(profile, cfg, state, day, attention, home) != offer:
                    return False
            elif (
                kind is not None
                or state.get("consumed") is not False
                or state.get("day") != offer.get("day")
                or self.clock() >= state.get("expires_at", 0)
                or offer.get("destination") != cfg.get("destination")
            ):
                return False
            now = self.clock()
            if kind in ("chores", "checkin", "household", "health"):
                state.update(
                    day=day, expires_at=now + 600, history=[], last_reply="", last_tools=[]
                )
            state.update(
                consumed=True,
                session_until=now + 600,
                turns=0,
                pending=None,
                claimed_at=now,
                invitation_kind=kind or "interest",
            )
            budget.update(day=day, count=budget["count"] + 1, last_attempt_at=now)
            records = [
                (profile, BUDGET, encode(budget), now),
                (profile, self.state_key, encode(state), now),
            ]
            if kind == "chores":
                records.append((profile, "conversation.chore_attempt", encode({"at": now}), now))
            store.db.executemany(
                "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) "
                "DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                records,
            )
            self.clear_since = None
            return True

    def context(self):
        with self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            p = setup.get("profile", SYSTEM)
            state = preference(s, p, self.state_key, {})
            if (
                not self.permitted(setup, preference(s, p, CONFIG, {}))
                or state.get("session_until", 0) <= self.clock()
                or state.get("turns", 0) >= self.turn_limit
            ):
                if state.get("pending") or state.get("last_reply"):
                    state.update(
                        pending=None, last_reply="", session_until=0, history=[], last_tools=[]
                    )
                    s.remember(p, self.state_key, state)
                return None
            from .amadeus_health import Health

            if state.get("invitation_kind") == "health" and not Health(s).session_allowed(p):
                state.update(
                    session_until=0, pending=None, last_reply="", history=[], last_tools=[]
                )
                s.remember(p, self.state_key, state)
                return None
            from .amadeus_feeds import context as feed_context

            return dict(
                profile=p,
                preferences=preference(s, p, "context.preferences", {}),
                source_context=feed_context(s, include_items=False),
                **state,
                **(
                    {
                        "capabilities": [
                            "A chore reminder was offered. Chores are marked done or snoozed with their NFC tag or dashboard; do not claim to change them without a tool."
                        ]
                    }
                    if state.get("invitation_kind") == "chores"
                    else {}
                ),
            )

    def end(self):
        with self.lock, self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            p = setup.get("profile", SYSTEM)
            state = preference(s, p, self.state_key, {})
            state.update(session_until=0, pending=None, last_reply="", history=[], last_tools=[])
            s.remember(p, self.state_key, state)

    def resume_reply(self):
        """Owner-requested retry: open input context without replaying an invitation."""
        with self.lock, self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            p = setup.get("profile", SYSTEM)
            cfg = preference(s, p, CONFIG, {})
            state = preference(s, p, self.state_key, {})
            if (
                not self.permitted(setup, cfg)
                or state.get("consumed") is not True
                or self.clock() >= state.get("expires_at", 0)
            ):
                raise ValueError("No recent invitation is available to resume")
            state.update(session_until=self.clock() + 600, turns=0, pending=None, last_reply="")
            s.remember(p, self.state_key, state)
        return {
            "ready_for_reply": True,
            "invitation_replayed": False,
            "reply_method": "push_to_talk",
        }

    def answer(self, text, generate):
        """User-initiated reply. Model proposes; only explicit confirmation writes taste."""
        with self.lock:
            context = self.context()
            if not context:
                return None
            lower = text.strip().lower().rstrip(".!?")
            if lower in (
                "stop",
                "not now",
                "skip",
                "leave me alone",
                "stop asking",
                "don't ask again",
            ):
                self.end()
                if lower in ("stop asking", "don't ask again"):
                    with self.store() as s:
                        cfg = preference(s, context["profile"], CONFIG, {})
                        cfg["enabled"] = False
                        s.remember(context["profile"], CONFIG, cfg)
                return "Of course. I'll leave it there."
            pending = context.get("pending")
            decision = confirmation_answer(text) if pending else None
            if pending and decision is True:
                with self.store() as s:
                    PreferenceConversation(s).confirm(
                        context["profile"],
                        pending["field"],
                        pending["values"],
                        scope="usually",
                        confirmed=True,
                        operation="append",
                    )
                self.end()
                return "Remembered. You can change or forget that in Amadeus setup."
            if pending and decision is False:
                self.end()
                return "No problem. I won't save it as a preference."
            result = generate(text, context)
            if context.get("invitation_kind") == "health" and not self.context():
                return None  # A room/privacy change during generation discards the reply.
            if not isinstance(result, dict) or set(result) != {"reply", "memory"}:
                raise ValueError("Invalid conversation result")
            reply = result["reply"]
            if (
                not isinstance(reply, str)
                or not 1 <= len(reply) <= 350
                or "<" in reply
                or "{" in reply
            ):
                raise ValueError("Invalid spoken reply")
            memory = result["memory"]
            if context.get("invitation_kind") in ("chores", "household", "health"):
                # Accepting/declining a reminder is neither task completion nor a
                # statement of taste. Chore sessions never harvest preferences.
                memory = None
            # Memory annotations are optional, untrusted output. A bad annotation
            # must not discard an otherwise valid reply or silently infer a field.
            valid_memory = (
                isinstance(memory, dict)
                and set(memory) == {"field", "values", "evidence"}
                and isinstance(memory["field"], str)
                and memory["field"] in FIELDS
                and isinstance(memory["values"], list)
                and 1 <= len(memory["values"]) <= 3
                and all(isinstance(v, str) and v.strip() and len(v) <= 80 for v in memory["values"])
                and isinstance(memory["evidence"], str)
                and bool(memory["evidence"].strip())
                and memory["evidence"].casefold() in text.casefold()
            )
            # Questions about the assistant or other people are not statements
            # of the owner's taste, even if the model recycles prior context.
            owner_question = bool(
                re.match(
                    r"\s*(what|what's|which|why|how|who|do you|does|are you|is your|can you)\b",
                    text,
                    re.I,
                )
            )
            if not valid_memory or owner_question:
                memory = None
            memory_status = None
            if memory is not None:
                from .preference_confidence import confidence, DEFAULTS, KEY as POLICY_KEY

                score = confidence(text, memory)
                memory = {**memory, "confidence": score}
                with self.store() as s:
                    policy = {**DEFAULTS, **preference(s, context["profile"], POLICY_KEY, {})}
                    if policy["auto_accept"] and score >= policy["threshold"]:
                        PreferenceConversation(s).confirm(
                            context["profile"],
                            memory["field"],
                            memory["values"],
                            scope="usually",
                            confirmed=True,
                            operation="append",
                            provenance="auto_accepted",
                        )
                        memory_status = dict(
                            field=memory["field"],
                            values=memory["values"],
                            confidence=score,
                            provenance="auto_accepted",
                        )
                        memory = None
            if memory is not None:
                # Supporting words validate the proposal but are not retained as a quote.
                memory = {
                    "field": memory["field"],
                    "values": memory["values"],
                    "confidence": memory["confidence"],
                }
                meaning = {
                    "genres": "you generally enjoy ",
                    "avoid": "you prefer to avoid ",
                    "liked_titles": "you like these titles: ",
                    "disliked_titles": "you dislike these titles: ",
                    "providers": "you use these streaming services: ",
                    "hobbies": "you enjoy these hobbies: ",
                    "personal_goals": "you want help making time for ",
                    "food_drink": "you prefer ",
                    "interests": "you are interested in ",
                }[memory["field"]]
                reply = "Should I remember that " + meaning + ", ".join(memory["values"]) + "?"
            with self.store() as s:
                state = preference(s, context["profile"], self.state_key, {})
                state.update(
                    pending=memory,
                    turns=state.get("turns", 0) + 1,
                    last_reply=reply,
                    memory_status=memory_status,
                )
                s.remember(context["profile"], self.state_key, state)
            return reply

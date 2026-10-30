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

from .amadeus import Store
from .amadeus_habits import preference
from .amadeus_onboarding import KEY, SYSTEM
from .amadeus_conversation import PreferenceConversation, FIELDS

CONFIG = "conversation.live"
STATE = "conversation.trial"


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

    def configure(self, *, enabled, destination):
        if (
            type(enabled) is not bool
            or not isinstance(destination, str)
            or not 1 <= len(destination) <= 100
        ):
            raise ValueError("Choose an enabled flag and registered destination")
        with self.lock, self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            if not setup or "door_presence" not in setup.get("sources", []):
                raise ValueError("Door observation consent required")
            s.remember(
                setup["profile"],
                CONFIG,
                dict(enabled=enabled, destination=destination, activated_at=self.clock()),
            )
            s.remember(
                setup["profile"], "conversation.preferences", dict(enabled=enabled, speech=enabled)
            )
            s.remember(setup["profile"], self.state_key, {})

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
            blocked = (
                presence_blocked
                or not self.permitted(setup, cfg)
                or not state
                or state.get("consumed") is not False
                or now >= state.get("expires_at", 0)
                or now < state.get("ready_after", now + 1)
                or destination != cfg.get("destination")
                or busy
                or calendar_busy
                or focus
                or media
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
            return dict(destination=cfg["destination"], day=state["day"])

    def claim(self, offer):
        # Caller rechecks attention and output route immediately before claiming.
        with self.lock, self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            p = setup.get("profile", SYSTEM)
            state = preference(s, p, self.state_key, {})
            cfg = preference(s, p, CONFIG, {})
            if (
                not self.permitted(setup, cfg)
                or state.get("consumed") is not False
                or state.get("day") != offer.get("day")
                or self.clock() >= state.get("expires_at", 0)
            ):
                return False
            state.update(consumed=True, session_until=self.clock() + 600, turns=0, pending=None)
            s.remember(p, self.state_key, state)
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
            from .amadeus_feeds import context as feed_context

            return dict(
                profile=p,
                preferences=preference(s, p, "context.preferences", {}),
                source_context=feed_context(s, include_items=False),
                **state,
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

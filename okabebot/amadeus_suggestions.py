"""Private delivery receipts and explicit feedback; never inferred taste or speech."""

from contextlib import closing
import hashlib
import json
import re
import secrets
import time
from pathlib import Path

from .amadeus import Store
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY

JOURNAL = "conversation.suggestions"
TOPICS = "conversation.topic_feedback"
REASONS = {
    "checkin": "You enabled optional check-ins. Your connected context indicated a quiet window at home, with no active focus session or media playback.",
    "interest": "You enabled optional check-ins after door activity. Your connected context later indicated a quiet moment.",
    "chores": "One of your enabled chore reminders was due, and your delivery settings allowed a gentle reminder.",
    "household": "A configured household observation qualified for an optional note and the delivery gates allowed it.",
    "health": "You opted into supportive coaching and its privacy and delivery gates allowed a check-in.",
}


class Suggestions:
    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = Path(folder), clock

    def store(self):
        return closing(Store(self.folder, clock=self.clock))

    @staticmethod
    def profile(store):
        setup = preference(store, SYSTEM, KEY, {})
        profile = setup.get("profile")
        choices = preference(store, profile or SYSTEM, "conversation.preferences", {})
        if (
            not profile
            or setup.get("paused") is not False
            or setup.get("guest") is not False
            or choices.get("enabled") is not True
        ):
            raise PermissionError("Private conversation consent is required")
        return profile

    def rows(self, store, profile):
        stored = preference(store, profile, JOURNAL, None)
        if stored is not None:
            return [
                r
                for r in stored.get("items", [])
                if 0 <= self.clock() - r.get("at", 0) <= 7 * 86400
            ]
        if preference(store, profile, "conversation.suggestion_legacy_disabled", False):
            return []
        # A previous version retained only a claim and a speech-delivery diagnostic.
        # Reconcile only matching successful delivery, never a claim alone.
        trial = preference(store, profile, "conversation.trial", {})
        try:
            diagnostic = json.loads(
                (self.folder.parent / "timing" / "amadeus-conversation.json").read_text()
            )
        except (OSError, ValueError):
            return []
        at = trial.get("claimed_at", 0)
        kind = trial.get("invitation_kind")
        if (
            trial.get("consumed") is not True
            or kind not in REASONS
            or diagnostic.get("state") != "delivered"
            or not 0 <= diagnostic.get("updated_at", 0) - at <= 600
            or not 0 <= self.clock() - at <= 7 * 86400
        ):
            return []
        identifier = hashlib.sha256(f"{profile}:{at}".encode()).hexdigest()[:32]
        return [
            {
                "id": identifier,
                "kind": kind,
                "at": at,
                "topic": None,
                "feedback": None,
                "legacy": True,
            }
        ]

    def record(self, kind, *, claimed_at, topic=None):
        from .amadeus_conversation import FIELDS

        if kind not in REASONS or topic is not None and topic not in FIELDS:
            raise ValueError("Use a supported delivered suggestion kind/topic")
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            profile = self.profile(store)
            trial = preference(store, profile, "conversation.trial", {})
            if trial.get("consumed") is not True or trial.get("claimed_at") != claimed_at:
                raise ValueError("A matching claimed delivery is required")
            rows = self.rows(store, profile)
            existing = next(
                (r for r in rows if r.get("claimed_at", r.get("at")) == claimed_at), None
            )
            if existing:
                return existing
            receipt = {
                "id": secrets.token_hex(16),
                "kind": kind,
                "at": self.clock(),
                "claimed_at": claimed_at,
                "topic": topic,
                "feedback": None,
            }
            store.remember(profile, JOURNAL, {"items": (rows + [receipt])[-8:]})
            if topic:
                recent = preference(store, profile, "conversation.topic_recency", {})
                recent[topic] = self.clock()
                store.remember(profile, "conversation.topic_recency", recent)
            return receipt

    def explanation(self):
        with self.store() as store:
            profile = self.profile(store)
            rows = self.rows(store, profile)
            if not rows:
                return {"available": False}
            value = rows[-1]
            if value.get("kind") == "health":
                from .amadeus_health import Health

                if not Health(store).session_allowed(profile):
                    return {"available": False}
            return {
                "available": True,
                "suggestion": {k: value.get(k) for k in ("id", "kind", "at", "topic", "feedback")}
                | {
                    "reason": REASONS.get(
                        value.get("kind"), "The detailed reason was not retained."
                    )
                },
            }

    def feedback(self, data):
        if (
            not isinstance(data, dict)
            or set(data) != {"suggestion_id", "outcome"}
            or not isinstance(data["suggestion_id"], str)
            or not re.fullmatch(r"[a-f0-9]{32}", data["suggestion_id"])
            or data["outcome"] not in ("good_timing", "too_soon", "not_interested")
        ):
            raise ValueError("Choose feedback for one delivered suggestion")
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            profile = self.profile(store)
            rows = self.rows(store, profile)
            selected = next((r for r in rows if r["id"] == data["suggestion_id"]), None)
            if selected is None:
                raise ValueError(
                    "This suggestion is no longer available; refresh before giving feedback"
                )
            if selected.get("feedback") == data["outcome"]:
                return {"saved": True, "outcome": data["outcome"]}
            pause = preference(store, profile, "conversation.feedback_pause", {})
            if pause.get("suggestion_id") == selected["id"] and data["outcome"] != "too_soon":
                store.forget(profile, key="conversation.feedback_pause")
            topics = preference(store, profile, TOPICS, {})
            previous = topics.get(selected.get("topic"), {})
            if (
                previous.get("suggestion_id") == selected["id"]
                and data["outcome"] != "not_interested"
            ):
                topics.pop(selected.get("topic"), None)
                store.remember(profile, TOPICS, topics)
            selected.update(feedback=data["outcome"], feedback_at=self.clock())
            store.remember(profile, JOURNAL, {"items": rows[-8:]})
            if data["outcome"] == "too_soon" and selected.get("kind") in ("interest", "checkin"):
                cfg = preference(store, profile, "conversation.live", {})
                store.remember(
                    profile,
                    "conversation.feedback_pause",
                    {
                        "until": self.clock() + cfg.get("min_gap_minutes", 120) * 60,
                        "suggestion_id": selected["id"],
                    },
                )
            if selected.get("topic") and data["outcome"] == "not_interested":
                topics = preference(store, profile, TOPICS, {})
                topics[selected["topic"]] = {
                    "at": self.clock(),
                    "outcome": "not_interested",
                    "suggestion_id": selected["id"],
                }
                store.remember(profile, TOPICS, topics)
            return {"saved": True, "outcome": data["outcome"]}

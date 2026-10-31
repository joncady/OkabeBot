"""Private preference elicitation policy; no microphone, inference or speech dispatcher.

A trusted conversation adapter supplies availability and explicit user confirmation.
Never interpret silence, playback history or generated model text as consent.
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY

QUESTIONS = {
    "entertainment": "What are you in the mood for—and is that just tonight, or usually your thing?",
    "hobbies": "What do you enjoy making time for when you have a little space?",
    "goals": "What would you most like a little help making time for?",
}
FIELDS = {
    "genres": "media",
    "avoid": "media",
    "liked_titles": "media",
    "disliked_titles": "media",
    "providers": "media",
    "hobbies": None,
    "personal_goals": None,
    "food_drink": None,
    "interests": None,
}


RECENCY_KEY = "conversation.preference_recency"


def opening_preferences(store, subject, *, now, cooldown_hours):
    """Exclude newly learned fields from unsolicited openers, without forgetting them."""
    prefs = json.loads(json.dumps(preference(store, subject, "context.preferences", {})))
    recency = preference(store, subject, RECENCY_KEY, {})
    # Older profiles only retain the last learned category; use that timestamp
    # conservatively rather than pretending every old preference was just learned.
    row = store.db.execute(
        "SELECT value,updated_at FROM preferences WHERE subject=? AND key=?",
        (subject, "conversation.last_memory"),
    ).fetchone()
    if row:
        last = json.loads(row[0])
        field = last.get("field")
        if field in FIELDS and field not in recency:
            recency = {**recency, field: row[1]}
    for key in ("conversation.topic_recency", "conversation.topic_feedback"):
        for field, value in preference(store, subject, key, {}).items():
            at = value.get("at") if isinstance(value, dict) else value
            if field in FIELDS and isinstance(at, (int, float)):
                recency = {**recency, field: max(recency.get(field, 0), at)}
    excluded = []
    if cooldown_hours > 0:
        for field, parent in FIELDS.items():
            at = recency.get(field)
            if isinstance(at, (int, float)) and 0 <= now - at < cooldown_hours * 3600:
                target = prefs.get(parent, {}) if parent else prefs
                if isinstance(target, dict) and field in target:
                    target.pop(field)
                    excluded.append(field)
                if parent and not target:
                    prefs.pop(parent, None)
    return prefs, excluded


class PreferenceConversation:
    def __init__(self, store):
        self.store = store

    def offer(
        self,
        subject,
        topic,
        *,
        requested=False,
        conversation_ending=False,
        available=False,
        identity_confirmed=False,
        private_surface=False,
        media_playing=True,
        quiet=True,
        speech_opt_in=False,
    ):
        setup = preference(self.store, SYSTEM, KEY, {})
        if (
            setup.get("profile") != subject
            or setup.get("paused") is not False
            or setup.get("guest") is not False
        ):
            return {"allowed": False, "reason": "private_setup_required"}
        if topic not in QUESTIONS:
            raise ValueError("Unsupported preference topic")
        settings = preference(self.store, subject, "conversation.preferences", {})
        if settings.get("enabled") is not True:
            return {"allowed": False, "reason": "not_opted_in"}
        if not all(v is True for v in (available, identity_confirmed, private_surface)):
            return {"allowed": False, "reason": "availability_unknown"}
        if media_playing is not False or quiet is not False:
            return {"allowed": False, "reason": "protected_window"}
        if not (requested is True or conversation_ending is True):
            return {"allowed": False, "reason": "no_conversation_opening"}
        today = (
            datetime.fromtimestamp(self.store.clock(), ZoneInfo(setup["timezone"]))
            .date()
            .isoformat()
        )
        if preference(self.store, subject, "conversation.last_question", {}).get("day") == today:
            return {"allowed": False, "reason": "daily_limit"}
        return {
            "allowed": True,
            "topic": topic,
            "text": QUESTIONS[topic],
            "speech": speech_opt_in is True and settings.get("speech") is True,
            "day": today,
            "requires_delivery_ack": True,
        }

    def delivered(self, subject, offer):
        # Caller must revalidate offer immediately before rendering and ACK only actual delivery.
        if offer.get("allowed") is not True or offer.get("topic") not in QUESTIONS:
            raise ValueError("A permitted delivered question is required")
        self.store.remember(
            subject, "conversation.last_question", {"day": offer["day"], "topic": offer["topic"]}
        )

    def confirm(
        self,
        subject,
        field,
        values,
        *,
        scope,
        confirmed=False,
        operation="replace",
        provenance="user_confirmed",
    ):
        setup = preference(self.store, SYSTEM, KEY, {})
        settings = preference(self.store, subject, "conversation.preferences", {})
        if (
            setup.get("profile") != subject
            or setup.get("paused") is not False
            or setup.get("guest") is not False
            or settings.get("enabled") is not True
        ):
            raise PermissionError("Private opted-in profile required")
        if provenance not in ("user_confirmed", "auto_accepted"):
            raise ValueError("Unsupported memory provenance")
        if operation not in ("replace", "append"):
            raise ValueError("Choose a supported preference update")
        if confirmed is not True or scope not in ("usually", "this_conversation"):
            raise ValueError("Confirm the meaning and duration before remembering")
        if field not in FIELDS or not isinstance(values, list) or not 1 <= len(values) <= 20:
            raise ValueError("Use supported bounded preference values")
        if any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in values):
            raise ValueError("Use short explicit preferences")
        if scope == "this_conversation":
            return {"stored": False, "scope": scope, "field": field, "values": values}
        prefs = preference(self.store, subject, "context.preferences", {})
        target = prefs.setdefault(FIELDS[field], {}) if FIELDS[field] else prefs
        previous = target.get(field, []) if operation == "append" else []
        if not isinstance(previous, list):
            raise ValueError("Existing preference needs owner correction")
        target[field] = list(dict.fromkeys(previous + values))
        if len(json.dumps(prefs)) > 4000:
            raise ValueError("Preference store exceeds the bounded context budget")
        self.store.remember(subject, "context.preferences", prefs)
        recent = preference(self.store, subject, RECENCY_KEY, {})
        recent = {k: v for k, v in recent.items() if k in FIELDS}
        recent[field] = self.store.clock()
        self.store.remember(subject, RECENCY_KEY, recent)
        self.store.remember(
            subject, "conversation.last_memory", {"field": field, "provenance": provenance}
        )
        return {
            "stored": True,
            "scope": scope,
            "field": field,
            "provenance": provenance,
            "operation": operation,
        }

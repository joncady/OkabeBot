"""Opt-in coaching policy shared by private setup and morning invitations.

No health inference, autonomous delivery or audio analysis.
"""

from datetime import datetime
import math
from zoneinfo import ZoneInfo

from .amadeus import identifier


TOPICS = {
    "movement": "Would a short movement break feel good?",
    "rest": "Would you like a little time to wind down?",
    "hydration": "Would you like a drink break?",
    "meals": "Want help planning a meal that sounds good?",
}
SETTINGS = "health.coaching"
DELIVERY = "health.coaching.delivery"


def valid_settings(value):
    return (
        isinstance(value, dict)
        and type(value.get("version")) is int
        and value["version"] == 1
        and type(value.get("enabled")) is bool
        and value.get("choice") in ("choose_topics", "not_now", "no")
        and isinstance(value.get("topics"), list)
        and all(isinstance(t, str) and t in TOPICS for t in value["topics"])
        and (not value["enabled"] or (value["choice"] == "choose_topics" and bool(value["topics"])))
        and type(value.get("paused_until")) in (int, float)
        and math.isfinite(value["paused_until"])
        and value["paused_until"] >= 0
    )


class Coaching:
    """A private store-backed policy used by owner setup and morning briefing.

    Callers must bind subject identity and permissions. Planning never sends a
    notification; record_delivery is called only after an actual delivery ACK.
    Explicit feedback is authoritative. Tone/sentiment is not an input.
    """

    def __init__(self, store, *, timezone="UTC"):
        self.store = store
        self.zone = ZoneInfo(timezone)

    def _get(self, subject, key):
        identifier(subject)
        return next(
            (p["value"] for p in self.store.recall(subject)["preferences"] if p["key"] == key), None
        )

    def invitation(self, subject):
        if self._get(subject, SETTINGS) is not None:
            return None
        return {
            "question": "Would you like optional, gentle support for habits you choose?",
            "choices": ["choose_topics", "not_now", "no"],
            "enabled_by_default": False,
        }

    def configure(self, subject, *, choice, topics=()):
        if choice not in ("choose_topics", "not_now", "no"):
            raise ValueError("Choose topics, not now, or no")
        if not isinstance(topics, (list, tuple)) or any(
            not isinstance(t, str) or t not in TOPICS for t in topics
        ):
            raise ValueError("Use supported user-selected topics")
        if (choice == "choose_topics") != bool(topics):
            raise ValueError("Opt-in requires topics; declines cannot contain topics")
        value = {
            "version": 1,
            "enabled": choice == "choose_topics",
            "choice": choice,
            "topics": sorted(set(topics)),
            "paused_until": 0,
        }
        self.store.remember(subject, SETTINGS, value)
        return value

    def plan(
        self,
        subject,
        topic,
        *,
        opportunity=False,
        available=False,
        private_surface=False,
        identity_confirmed=False,
        quiet=True,
    ):
        permission = self._get(subject, SETTINGS)
        if not valid_settings(permission):
            return {"allowed": False, "reason": "not_configured"}
        if permission.get("enabled") is not True or topic not in permission.get("topics", []):
            return {"allowed": False, "reason": "not_opted_in"}
        now = self.store.clock()
        if permission.get("paused_until", 0) > now:
            return {"allowed": False, "reason": "paused"}
        if not all(
            v is True for v in (opportunity, available, private_surface, identity_confirmed)
        ):
            return {"allowed": False, "reason": "context_not_confirmed"}
        if quiet is not False:
            return {"allowed": False, "reason": "quiet"}
        last = self._get(subject, DELIVERY)
        if last is not None and (
            not isinstance(last, dict)
            or not isinstance(last.get("day"), str)
            or type(last.get("delivered_at")) not in (int, float)
            or not math.isfinite(last["delivered_at"])
        ):
            return {"allowed": False, "reason": "invalid_delivery_state"}
        today = datetime.fromtimestamp(now, self.zone).date().isoformat()
        if isinstance(last, dict) and last.get("day") == today:
            return {"allowed": False, "reason": "daily_limit"}
        if isinstance(last, dict) and last.get("delivered_at", 0) + 3600 > now:
            return {"allowed": False, "reason": "cooldown"}
        if topic not in TOPICS:
            return {"allowed": False, "reason": "unsupported_topic"}
        return {
            "allowed": True,
            "topic": topic,
            "text": TOPICS[topic],
            "presentation": "quiet_card",
            "speech": False,
        }

    def record_delivery(self, subject, topic):
        if topic not in TOPICS:
            raise ValueError("Unsupported topic")
        self.store.remember(
            subject,
            DELIVERY,
            {
                "day": datetime.fromtimestamp(self.store.clock(), self.zone).date().isoformat(),
                "topic": topic,
                "delivered_at": self.store.clock(),
            },
        )

    def feedback(self, subject, outcome, *, topic=None):
        if outcome not in ("helpful", "later", "not_helpful", "stop", "topic_off", "resume"):
            raise ValueError("Use explicit feedback; inferred sentiment is not accepted")
        value = self._get(subject, SETTINGS)
        if not valid_settings(value):
            raise ValueError("Configure coaching before feedback")
        if outcome == "stop":
            value["enabled"] = False
        elif outcome == "resume":
            if value["choice"] != "choose_topics" or not value["topics"]:
                raise ValueError("Choose coaching topics before resuming")
            value.update(enabled=True, paused_until=0)
        elif outcome in ("later", "not_helpful"):
            value["paused_until"] = self.store.clock() + 86400
        elif outcome == "topic_off":
            if topic not in TOPICS:
                raise ValueError("Choose the topic to turn off")
            value["topics"] = [t for t in value["topics"] if t != topic]
            value["enabled"] = bool(value["topics"]) and value["enabled"]
        # Helpful never increases frequency or authorizes another topic.
        self.store.remember(subject, SETTINGS, value)
        return value

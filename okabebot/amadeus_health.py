"""Private owner-selected wellbeing goals; no clinical inference or identity detection."""

from datetime import datetime
import json
from zoneinfo import ZoneInfo

from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY

CONFIG = "health.goals"
DEFAULTS = {"enabled": False, "daily_steps": 0, "nudge_after": 17, "others_detected": False}


def settings(store):
    return {**DEFAULTS, **preference(store, SYSTEM, CONFIG, {})}


def others_detected(store):
    if settings(store)["others_detected"]:
        return True
    cfg = preference(store, SYSTEM, "feed.health", {})
    if not cfg.get("others"):
        return False  # Explicit prototype default; not a claim of verified solitude.
    setup = preference(store, SYSTEM, KEY, {})
    if (
        not cfg.get("enabled")
        or setup.get("paused")
        or setup.get("guest")
        or "health" not in setup.get("sources", [])
    ):
        return True
    row = store.db.execute(
        "SELECT payload FROM events WHERE source='health' AND kind='feed_snapshot' AND subject=? AND expires_at>? AND observed_at<=? ORDER BY observed_at DESC,rowid DESC LIMIT 1",
        (setup.get("profile", ""), store.clock(), store.clock()),
    ).fetchone()
    if not row:
        return True
    value = json.loads(row[0])
    signals = [i for i in value["items"] if i.get("metric") == "others"]
    return (
        value["valid_until_at"] <= store.clock()
        or len(signals) != len(cfg["others"])
        or any(
            i.get("value") != "off" or not 0 <= store.clock() - i.get("sample_at", 0) <= 900
            for i in signals
        )
    )


class Health:
    def __init__(self, store):
        self.store = store

    def configure(self, value):
        if not isinstance(value, dict) or set(value) != set(DEFAULTS):
            raise ValueError(
                "Choose health support, daily step goal, nudge hour and shared-room override"
            )
        if any(type(value[k]) is not bool for k in ("enabled", "others_detected")):
            raise ValueError("Choose enabled and others detected")
        if type(value["daily_steps"]) is not int or not 0 <= value["daily_steps"] <= 100000:
            raise ValueError("Choose a personal daily step goal, or zero for none")
        if type(value["nudge_after"]) is not int or not 0 <= value["nudge_after"] <= 23:
            raise ValueError("Choose a local nudge hour")
        self.store.remember(SYSTEM, CONFIG, value)
        return self.snapshot()

    def session_allowed(self, profile):
        """Ongoing consent, separate from offer timing and already-delivered cooldowns."""
        from .amadeus_coaching import SETTINGS, valid_settings

        s = self.store
        setup = preference(s, SYSTEM, KEY, {})
        cfg = settings(s)
        feed = preference(s, SYSTEM, "feed.health", {})
        permission = preference(s, profile, SETTINGS)
        return bool(
            setup.get("profile") == profile
            and not setup.get("paused")
            and not setup.get("guest")
            and "health" in setup.get("sources", [])
            and cfg["enabled"]
            and cfg["daily_steps"]
            and feed.get("enabled")
            and feed.get("daily_steps")
            and valid_settings(permission)
            and permission["enabled"]
            and "movement" in permission["topics"]
            and permission["paused_until"] <= s.clock()
            and not others_detected(s)
        )

    def offer(self, *, morning=False):
        from .amadeus_coaching import Coaching, DELIVERY
        from .amadeus_feeds import context

        s = self.store
        setup = preference(s, SYSTEM, KEY, {})
        cfg = settings(s)
        profile = setup.get("profile")
        if not profile or not self.session_allowed(profile):
            return None
        policy = Coaching(s, timezone=setup["timezone"])
        local = datetime.fromtimestamp(s.clock(), ZoneInfo(setup["timezone"]))
        last = policy._get(profile, DELIVERY)
        if last and (
            last.get("day") == local.date().isoformat()
            or last.get("delivered_at", 0) + 3600 > s.clock()
        ):
            return None
        items = next((f["items"] for f in context(s) if f["source"] == "health"), [])
        steps = [
            i
            for i in items
            if i.get("metric") == "daily_steps"
            and 0 <= s.clock() - i.get("sample_at", 0) <= 3600
            and datetime.fromtimestamp(i["sample_at"], ZoneInfo(setup["timezone"])).date()
            == local.date()
        ]
        if len(steps) != 1:
            return None
        achieved = float(steps[0]["value"]) >= cfg["daily_steps"]
        if not achieved and not morning and local.hour < cfg["nudge_after"]:
            return None
        return {
            "topic": "movement",
            "outcome": "achieved" if achieved else "invitation",
            "text": "You reached the movement goal you chose today. Nice work making time for yourself."
            if achieved
            else "If a short walk sounds good today, there is room to work toward the movement goal you chose. No pressure.",
            "goal": cfg["daily_steps"],
        }

    def snapshot(self):
        from .amadeus_feeds import context

        blocked = others_detected(self.store)
        return {
            "settings": settings(self.store),
            "others_detected": blocked,
            "privacy": "Health discussion suppressed"
            if blocked
            else "Others detection defaults false until sensors are configured",
            "readings": next(
                (f["items"] for f in context(self.store) if f["source"] == "health"), []
            ),
            "offer": self.offer(),
        }

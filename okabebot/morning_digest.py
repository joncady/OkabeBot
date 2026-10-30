"""Bounded, grounded morning highlights from existing consented context; no new reads."""

from datetime import datetime
from zoneinfo import ZoneInfo

from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY

CONFIG = "morning.digest"
DEFAULTS = {"tasks": True, "transit": True, "meals": True, "spoken_highlight": True}


class Digest:
    def __init__(self, store):
        self.store = store

    def settings(self):
        return {**DEFAULTS, **preference(self.store, SYSTEM, CONFIG, {})}

    def configure(self, value):
        if (
            not isinstance(value, dict)
            or set(value) != set(DEFAULTS)
            or any(type(v) is not bool for v in value.values())
        ):
            raise ValueError("Choose the morning sections and spoken highlight")
        self.store.remember(SYSTEM, CONFIG, value)
        return self.settings()

    def cards(self):
        from .amadeus_feeds import context

        setup = preference(self.store, SYSTEM, KEY, {})
        if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
            return []
        zone = ZoneInfo(setup["timezone"])
        now = self.store.clock()
        today = datetime.fromtimestamp(now, zone).date()
        enabled = self.settings()
        cards, seen = [], set()
        # Use the full stable-item view, not the first compatibility-preview page.
        for feed in context(self.store, full=True, sources={"transit", "tasks", "meals"}):
            source = feed["source"]
            if source not in ("transit", "tasks", "meals") or not enabled[source]:
                continue
            count = 0
            ranks = {"NO_SERVICE": 0, "SIGNIFICANT_DELAYS": 1, "REDUCED_SERVICE": 2, "DETOUR": 3}
            items = sorted(
                feed["items"],
                key=lambda i: (
                    (ranks.get(i.get("effect"), 9), i["id"])
                    if source == "transit"
                    else (i.get("due" if source == "tasks" else "start", "9999"), i["id"])
                ),
            )
            for item in items:
                title = item.get("title", "").strip()
                key = (title.casefold(), item.get("due", ""), item.get("start", ""))
                if not title or key in seen or count >= 2:
                    continue
                spoken, priority = None, 0
                if source == "transit":
                    label = "On your rail lines"
                    body = title
                    spoken = "On your selected rail lines: " + title
                    priority = 3
                elif source == "tasks":
                    if item.get("state") != "needs_action" or not item.get("due"):
                        continue
                    try:
                        raw = item["due"]
                        due = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                        date = due.astimezone(zone).date() if due.tzinfo else due.date()
                    except (ValueError, TypeError):
                        continue
                    if date > today:
                        continue
                    overdue = date < today
                    label = "Still on your list" if overdue else "Due today"
                    body = title
                    spoken = ("Still on your list: " if overdue else "Due today: ") + title
                    priority = 2
                else:
                    if item.get("category") != "meal_plan":
                        continue
                    try:
                        start = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
                        date = start.astimezone(zone).date() if start.tzinfo else start.date()
                    except (KeyError, ValueError, TypeError):
                        continue
                    if date != today:
                        continue
                    label, body = "On today's menu", title
                    spoken, priority = "Your meal plan lists " + title, 1
                seen.add(key)
                count += 1
                cards.append(
                    {
                        "kind": source,
                        "title": label,
                        "body": body[:180],
                        "spoken": spoken[:200],
                        "priority": priority,
                        "source": source,
                        "partial": not feed["complete"],
                        "important": source == "transit",
                    }
                )
        return sorted(cards, key=lambda c: -c["priority"])

    def highlight(self):
        if not self.settings()["spoken_highlight"]:
            return None
        return next(iter(self.cards()), None)

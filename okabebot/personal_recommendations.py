"""Read explicit private context for personalized ideas; never infer taste or act."""

from contextlib import closing
from .amadeus import Store
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY

TOPICS = {
    "activities": ("hobbies", "interests"),
    "food": ("food_drink",),
    "goals": ("personal_goals",),
}


def recommendation_context(folder, topic="activities"):
    if topic not in (*TOPICS, "all"):
        raise ValueError("Choose activities, food, goals or all")
    with closing(Store(folder)) as store:
        setup = preference(store, SYSTEM, KEY, {})
        profile = setup.get("profile")
        choices = preference(store, profile or SYSTEM, "conversation.preferences", {})
        if (
            not profile
            or setup.get("paused") is not False
            or setup.get("guest") is not False
            or choices.get("enabled") is not True
        ):
            return {"state": "private_context_unavailable", "preferences": {}}
        from .amadeus_health import others_detected

        if others_detected(store):
            return {"state": "privacy_blocked", "preferences": {}}
        saved = preference(store, profile, "context.preferences", {})
        fields = sum(TOPICS.values(), ()) if topic == "all" else TOPICS[topic]
        selected = {
            field: saved[field]
            for field in fields
            if isinstance(saved.get(field), list) and saved[field]
        }
        return {
            "topic": topic,
            "preferences": selected,
            "provenance": "Explicit saved preferences only; not observations or inferred interests",
            "missing": [
                "Current energy, available time and desire for an activity are unknown unless supplied this turn",
                "Ingredient inventory and availability have not been checked",
            ],
            "scope": "Context for optional personalized ideas, not an obligation or authorization. No health readings, purchases, memory writes or actions. An anecdote is not a new preference.",
        }

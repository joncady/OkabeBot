"""Grounded on-demand watchlist choices; no inference, collection or account writes."""

from .amadeus_feeds import Feeds, context
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY
from .trakt_library import watchlist


def genre_key(value):
    value = value.strip().casefold().replace("_", "-").replace(" ", "-")
    return {"sci-fi": "science-fiction", "scifi": "science-fiction"}.get(value, value)


def recommendations(folder, *, kind="movies", page=1, genre="", max_minutes=None, read=None):
    if not isinstance(genre, str) or len(genre) > 50:
        raise ValueError("Use one short genre or leave it blank")
    if max_minutes is not None and (type(max_minutes) is not int or not 1 <= max_minutes <= 600):
        raise ValueError("Choose a maximum runtime from 1 to 600 minutes")
    library = watchlist(folder, page=page, kind=kind, **({"read": read} if read else {}))
    if library.get("state"):
        return {**library, "availability": "not_checked"}
    feeds = Feeds(folder)
    with feeds.store() as store:
        setup = preference(store, SYSTEM, KEY, {})
        if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
            return {"items": [], "state": "context_changed", "availability": "not_checked"}
        prefs = preference(store, setup["profile"], "context.preferences", {})
        history_settings = preference(store, SYSTEM, "feed.watch_history", {})
        history = context(store, full=True, sources={"watch_history"})
        seen = {
            (item.get("type"), str(item["trakt_id"]))
            for snapshot in history
            for item in snapshot["items"]
            if item.get("trakt_id")
            and item.get("watch_state") in ("watched", "watched_date_unknown")
        }
        profile = setup["profile"]
    preferred = {
        genre_key(v) for v in prefs.get("media", {}).get("genres", []) if isinstance(v, str)
    }
    requested = genre_key(genre)
    items, excluded, unknown, no_match = [], 0, 0, 0
    for item in library.get("items", []):
        if (item["type"], item["id"]) in seen:
            excluded += 1
            continue
        genres = {genre_key(v) for v in item.get("genres", [])}
        runtime = item.get("runtime_minutes")
        if (requested and not genres) or (max_minutes is not None and runtime is None):
            unknown += 1
            continue
        if (requested and requested not in genres) or (
            max_minutes is not None and runtime > max_minutes
        ):
            no_match += 1
            continue
        why = ["Saved on your want-to-watch list"]
        if requested:
            why.append("Matches the requested genre: " + genre)
        overlap = sorted(preferred & genres)
        if overlap:
            why.append("Matches a saved genre: " + ", ".join(overlap))
        if max_minutes is not None:
            why.append(f"Reported runtime fits the {max_minutes}-minute limit")
        items.append({**item, "why_fit": why, "_score": len(overlap)})
    items.sort(key=lambda i: -i["_score"])
    for item in items:
        item.pop("_score")
    # Recheck after deriving private preference/history evidence as well as the
    # connection checks performed by the watchlist reader.
    with feeds.store() as store:
        if preference(store, SYSTEM, KEY, {}) != setup:
            return {"items": [], "state": "context_changed", "availability": "not_checked"}
        current = preference(store, profile, "context.preferences", {})
        if (
            current != prefs
            or preference(store, SYSTEM, "feed.watch_history", {}) != history_settings
        ):
            return {"items": [], "state": "context_changed", "availability": "not_checked"}
    return {
        **library,
        "items": items,
        "criteria": {"genre": genre, "max_minutes": max_minutes},
        "availability": "not_checked",
        "known_watched_excluded": excluded,
        "unknown_metadata_excluded": unknown,
        "criteria_mismatch_excluded": no_match,
        "history_coverage": "selected_cached_scope" if history else "unknown",
        "scope": "Choices from this Trakt watchlist page only. Known watched stable IDs from current consented cached history and selected date-unknown watched lists are excluded. History is partial, not lifetime coverage; remaining items are not guaranteed unwatched. Genres/runtime are optional cached Trakt metadata. Streaming availability has not been checked.",
    }


def fallback(result):
    if result.get("state"):
        return "I couldn't read your watchlist just now. Check the Trakt connection in setup."
    if not result.get("items"):
        return "I couldn't find a verified match on this watchlist page. We can loosen the genre or time limit; streaming availability hasn't been checked."
    item = result["items"][0]
    reason = next(
        (v for v in item.get("why_fit", []) if v.startswith("Matches") or v.startswith("Reported")),
        "it's on your want-to-watch list",
    )
    return f"I'd start with {item['title']}: {reason[0].lower() + reason[1:]}. Streaming availability hasn't been checked."

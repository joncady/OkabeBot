"""Owner-requested Trakt watchlist reads; no collection, writes or inferred tastes."""

from urllib.parse import urlencode
from .adapters.context.providers import request_page, clean
from .trakt_history import page_result
from .amadeus_feeds import Feeds
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY


def watchlist(folder, *, page=1, kind="movies", read=request_page):
    if type(page) is not int or not 1 <= page <= 1000 or kind not in ("movies", "shows", "all"):
        raise ValueError("Choose movies, shows or all and a page from 1 to 1000")
    feeds = Feeds(folder)
    with feeds.store() as store:
        setup = preference(store, SYSTEM, KEY, {})
        connection = preference(store, SYSTEM, "feed_connection.trakt", {})
        generation = preference(store, SYSTEM, "feed_connection_revision.trakt")
    if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
        return {"items": [], "state": "paused_or_not_configured"}
    if not connection.get("token") or not connection.get("client_id"):
        return {"items": [], "state": "authorize_trakt"}
    connection = feeds.trakt_auth.refresh(connection)
    with feeds.store() as store:
        if (
            preference(store, SYSTEM, KEY, {}) != setup
            or preference(store, SYSTEM, "feed_connection_revision.trakt") != generation
            or not connection.get("token")
            or not connection.get("client_id")
        ):
            return {"items": [], "state": "context_changed"}
    path = "sync/watchlist" + ("/" + kind if kind != "all" else "")
    value = read(
        "https://api.trakt.tv/"
        + path
        + "?"
        + urlencode({"limit": 20, "page": page, "extended": "full"}),
        {
            "Authorization": "Bearer " + connection["token"],
            "trakt-api-key": connection["client_id"],
            "trakt-api-version": "2",
            "User-Agent": "OkabeBot/0.1.0",
        },
    )
    rows, page_count, complete = page_result(value, page, requested=20)
    items = []
    for row in rows:
        media_type = row.get("type")
        if media_type not in ("movie", "show"):
            continue
        media = row.get(media_type, {})
        ident = media.get("ids", {}).get("trakt")
        title = media.get("title")
        if type(ident) is not int or not isinstance(title, str) or not title.strip():
            raise ValueError("Invalid watchlist identity")
        item = {
            "id": str(ident),
            "type": media_type,
            "title": clean(title),
            "year": media.get("year"),
        }
        # Extended embedded objects may be cached or incomplete. Missing metadata
        # stays unknown; never synthesize a genre/runtime from a title.
        genres = media.get("genres")
        if isinstance(genres, list) and all(isinstance(g, str) for g in genres):
            item["genres"] = [clean(g) for g in genres[:20] if g.strip()]
        runtime = media.get("runtime")
        if type(runtime) is int and 0 < runtime <= 1440:
            item["runtime_minutes"] = runtime
        items.append(item)
    with feeds.store() as store:
        if (
            preference(store, SYSTEM, KEY, {}) != setup
            or preference(store, SYSTEM, "feed_connection.trakt", {}) != connection
            or preference(store, SYSTEM, "feed_connection_revision.trakt") != generation
        ):
            return {"items": [], "state": "context_changed"}
    return {
        "items": items,
        "page": page,
        "next_page": page + 1 if (not complete and rows) else None,
        "complete": complete,
        "pagination_known": page_count is not None,
        "scope": "User's Trakt want-to-watch list, not viewing history, ratings, subscriptions or streaming availability. Recommend only supplied titles; explain that availability has not been checked.",
    }


def owned_lists(folder, *, page=1, read=request_page):
    """Explicit owner discovery only; no titles/items are written to memory."""
    if type(page) is not int or not 1 <= page <= 1000:
        raise ValueError("Choose a list-discovery page from 1 to 1000")
    feeds = Feeds(folder)
    with feeds.store() as store:
        setup = preference(store, SYSTEM, KEY, {})
        connection = preference(store, SYSTEM, "feed_connection.trakt", {})
        generation = preference(store, SYSTEM, "feed_connection_revision.trakt")
    if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
        return {"items": [], "state": "paused_or_not_configured"}
    if not connection.get("token") or not connection.get("client_id"):
        return {"items": [], "state": "authorize_trakt"}
    connection = feeds.trakt_auth.refresh(connection)
    with feeds.store() as store:
        if (
            preference(store, SYSTEM, KEY, {}) != setup
            or preference(store, SYSTEM, "feed_connection_revision.trakt") != generation
            or not connection.get("token")
            or not connection.get("client_id")
        ):
            return {"items": [], "state": "context_changed"}
    from .trakt_history import headers

    value = read(
        "https://api.trakt.tv/users/me/lists?" + urlencode({"page": page, "limit": 100}),
        headers(connection),
    )
    rows, count, complete = page_result(value, page)
    items = []
    for row in rows:
        ident = row.get("ids", {}).get("trakt")
        title = clean(row.get("name"))
        if type(ident) is not int or ident < 1 or not title:
            raise ValueError("Invalid owned-list identity")
        item_count = row.get("item_count")
        items.append(
            {
                "id": str(ident),
                "title": title,
                "item_count": item_count if type(item_count) is int and item_count >= 0 else None,
            }
        )
    with feeds.store() as store:
        if (
            preference(store, SYSTEM, KEY, {}) != setup
            or preference(store, SYSTEM, "feed_connection.trakt", {}) != connection
            or preference(store, SYSTEM, "feed_connection_revision.trakt") != generation
        ):
            return {"items": [], "state": "context_changed"}
    return {
        "items": items,
        "state": "connected",
        "page": page,
        "next_page": page + 1 if not complete and rows else None,
        "complete": complete,
        "pagination_known": count is not None,
        "scope": "Owned list names only; no collection is enabled. Select only lists whose items you explicitly regard as watched with unknown dates.",
    }

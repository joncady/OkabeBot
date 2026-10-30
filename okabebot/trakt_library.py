"""Owner-requested Trakt watchlist reads; no collection, writes or inferred tastes."""

from urllib.parse import urlencode
from .adapters.context.providers import request, clean
from .amadeus_feeds import Feeds
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY


def watchlist(folder, *, page=1, kind="movies", read=request):
    if type(page) is not int or not 1 <= page <= 1000 or kind not in ("movies", "shows", "all"):
        raise ValueError("Choose movies, shows or all and a page from 1 to 1000")
    feeds = Feeds(folder)
    with feeds.store() as store:
        setup = preference(store, SYSTEM, KEY, {})
        connection = preference(store, SYSTEM, "feed_connection.trakt", {})
    if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
        return {"items": [], "state": "paused_or_not_configured"}
    if not connection.get("token") or not connection.get("client_id"):
        return {"items": [], "state": "authorize_trakt"}
    connection = feeds.trakt_auth.refresh(connection)
    path = "sync/watchlist" + ("/" + kind if kind != "all" else "")
    rows = read(
        "https://api.trakt.tv/" + path + "?" + urlencode({"limit": 20, "page": page}),
        {
            "Authorization": "Bearer " + connection["token"],
            "trakt-api-key": connection["client_id"],
            "trakt-api-version": "2",
            "User-Agent": "OkabeBot/0.1.0",
        },
    )
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValueError("Invalid watchlist response")
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
        items.append(
            {"id": str(ident), "type": media_type, "title": clean(title), "year": media.get("year")}
        )
    with feeds.store() as store:
        if (
            preference(store, SYSTEM, KEY, {}) != setup
            or preference(store, SYSTEM, "feed_connection.trakt", {}) != connection
        ):
            return {"items": [], "state": "context_changed"}
    return {
        "items": items,
        "page": page,
        "next_page": page + 1 if len(rows) == 20 else None,
        "scope": "User's Trakt want-to-watch list, not viewing history, ratings, subscriptions or streaming availability. Recommend only supplied titles; explain that availability has not been checked.",
    }

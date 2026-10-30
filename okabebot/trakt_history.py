"""Read-only bounded Trakt history/list collection with explicit provenance.

Completeness describes the configured window plus selected list memberships,
never account lifetime, episode completion, tastes, subscriptions or availability.
"""

from collections import deque
from datetime import datetime, timezone
from urllib.parse import urlencode

from .adapters.context import FEEDS, validate_config
from .adapters.context.providers import ProviderPage, clean, identity, request_page, stamp
from .spotify import env_value


class CollectionCancelled(ValueError):
    """The owner changed the read's consent, settings or connection."""


def headers(connection):
    client = connection.get("client_id") or env_value("AMADEUS_TRAKT_CLIENT_ID")
    token = connection.get("token") or env_value("AMADEUS_TRAKT_ACCESS_TOKEN")
    if not client or not token:
        raise ValueError("Trakt authorization required")
    return {
        "Authorization": "Bearer " + token,
        "trakt-api-key": client,
        "trakt-api-version": "2",
        "User-Agent": "OkabeBot/0.1.0",
    }


def page_result(value, page, requested=100):
    """Do not infer exhaustion from the requested limit: Trakt can clamp it."""
    if isinstance(value, ProviderPage):
        rows, meta = value.body, {k.lower(): v for k, v in value.headers.items()}
    else:
        rows, meta = value, {}
    if not isinstance(rows, list) or len(rows) > requested:
        raise ValueError("Invalid Trakt page")
    try:
        current = int(meta["x-pagination-page"])
        count = int(meta["x-pagination-page-count"])
        limit = int(meta["x-pagination-limit"])
        if (
            current != page
            or not 0 <= count <= 1_000_000
            or not 1 <= limit <= requested
            or len(rows) > limit
            or (count == 0 and rows)
        ):
            raise ValueError("Inconsistent Trakt pagination")
    except KeyError:
        # A body-only reader or missing headers cannot certify completeness.
        return rows, None, False
    except (TypeError, ValueError):
        raise ValueError("Invalid Trakt pagination") from None
    return rows, count, current >= count


def normalize_history(rows, start, end):
    items = []
    for row in rows:
        kind = row.get("type")
        if kind not in ("movie", "episode"):
            continue
        event_id = row.get("id")
        if type(event_id) is not int or event_id < 1:
            raise ValueError("Invalid Trakt history identity")
        watched = stamp(row["watched_at"])
        if not start <= watched <= end:
            continue
        media = row[kind]
        title = clean(media.get("title"))
        if not title:
            raise ValueError("Missing Trakt title")
        item = {
            "id": identity(event_id),
            "title": title,
            "type": kind,
            "watched_at": watched,
            "watch_state": "watched",
            "provenance": "trakt_history",
        }
        media_id = media.get("ids", {}).get("trakt")
        if type(media_id) is int and media_id > 0:
            item["trakt_id"] = str(media_id)
        if kind == "episode" and row.get("show", {}).get("title"):
            item["show"] = clean(row["show"]["title"])
        items.append(item)
    return items


def normalize_list(rows, list_id):
    items = []
    for row in rows:
        kind = row.get("type")
        if kind not in ("movie", "show", "episode"):
            continue
        media = row.get(kind, {})
        media_id = media.get("ids", {}).get("trakt")
        title = clean(media.get("title"))
        if type(media_id) is not int or media_id < 1 or not title:
            raise ValueError("Invalid Trakt list identity")
        item = {
            "id": identity(["trakt-list", list_id, kind, media_id]),
            "title": title,
            "type": kind,
            "list_id": list_id,
            "watch_state": "watched_date_unknown",
            "provenance": "owner_selected_trakt_list",
            "trakt_id": str(media_id),
        }
        if kind == "episode" and row.get("show", {}).get("title"):
            item["show"] = clean(row["show"]["title"])
        # listed_at is deliberately not a watched date.
        items.append(item)
    return items


def collect(cfg, now, connection=None, *, read=request_page, allowed=lambda: True):
    cfg = validate_config(FEEDS["watch_history"], cfg)
    start = now - cfg["history_days"] * 86400
    query = {
        "start_at": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "end_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
    }
    queue = deque([{"path": "sync/history", "query": query, "page": 1, "list_id": None}])
    for list_id in cfg["watched_lists"]:
        queue.append(
            {"path": f"users/me/lists/{list_id}/items", "query": {}, "page": 1, "list_id": list_id}
        )
    collected, answered, incomplete = {}, 0, False
    auth = headers(connection or {})
    for _ in range(cfg["page_budget"]):
        if not queue:
            break
        if not allowed():
            raise CollectionCancelled("Trakt read cancelled after context changed")
        source = queue.popleft()
        url = (
            "https://api.trakt.tv/"
            + source["path"]
            + "?"
            + urlencode({**source["query"], "limit": 100, "page": source["page"]})
        )
        try:
            rows, count, complete = page_result(read(url, auth), source["page"])
            if "page_count" in source and source["page_count"] != count:
                # List/account changes mid-read are not a consistent snapshot.
                incomplete = True
            source["page_count"] = count
            normalized = (
                normalize_list(rows, source["list_id"])
                if source["list_id"]
                else normalize_history(rows, start, now)
            )
            answered += 1
            for item in normalized:
                prior = collected.get(item["id"])
                if prior is not None and prior != item:
                    raise ValueError("Conflicting Trakt identity")
                collected[item["id"]] = item
            if not complete:
                if rows and count is not None:
                    source["page"] += 1
                    queue.append(source)
                else:
                    incomplete = True
        except CollectionCancelled:
            raise
        except Exception:
            # Preserve successful sources/pages, but never certify deletion on a failed read.
            incomplete = True
    if not allowed():
        raise CollectionCancelled("Trakt read cancelled after context changed")
    if not answered:
        raise ValueError("Trakt source read unavailable")
    return list(collected.values()), not incomplete and not queue

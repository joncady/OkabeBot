"""Opt-in private context feeds with one registry and no notification/device access."""

from contextlib import closing
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
import uuid
import time

from .adapters.context import (
    FEEDS,
    validate_config,
    validate_snapshot,
    TRAKT_DEFAULTS,
    TRAKT_OPTIONS,
)
from .adapters.context.providers import fetch
from .amadeus import Store, encode
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY
from .amadeus_sources import digest

PREFIX = "feed."


def default(feed):
    return dict(
        **({**TRAKT_DEFAULTS, "watched_lists": []} if feed.id == "watch_history" else {}),
        enabled=False,
        **{
            f[0]: ["1", "2"] if feed.id == "transit" and f[0] == "routes" else []
            for f in feed.fields
        },
    )


def coverage_scope(feed, cfg):
    if feed.id != "watch_history":
        return {}
    return {
        "scope": f"Trakt collection covers the configured {cfg['history_days']}-day history window plus explicitly selected watched-date-unknown lists. Completeness is limited to that scope, not lifetime history, episode completion, tastes or streaming availability. Retained changes may contain earlier observations; list membership supplies no watched date."
    }


def permitted(setup, feed):
    return (
        bool(setup.get("profile"))
        and setup.get("paused") is False
        and setup.get("guest") is False
        and feed.id in setup.get("sources", [])
    )


def context(store, *, limit=12, include_items=True, full=False):
    """Latest fresh consented snapshots only; empty snapshots clear prior values."""
    setup = preference(store, SYSTEM, KEY, {})
    if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
        return []
    now, found, result = store.clock(), set(), []
    rows = store.db.execute(
        "SELECT source,payload,observed_at FROM events WHERE kind='feed_snapshot' AND expires_at>? "
        "AND observed_at<=? AND subject IN (?, 'unknown') ORDER BY observed_at DESC,rowid DESC",
        (now, now, setup["profile"]),
    )
    for row in rows:
        if row["source"] in found:
            continue
        found.add(row["source"])
        feed = FEEDS.get(row["source"])
        if not feed or not permitted(setup, feed):
            continue
        cfg = {**default(feed), **preference(store, SYSTEM, PREFIX + feed.id, {})}
        if not cfg["enabled"]:
            continue
        value = json.loads(row["payload"])
        if value["valid_until_at"] <= now:
            continue
        if (
            full
            and store.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='context_records'"
            ).fetchone()
        ):
            subject = "unknown" if feed.household else setup["profile"]
            records = store.db.execute(
                "SELECT payload FROM context_records WHERE source=? AND subject=? AND expires_at>? AND valid_until>? ORDER BY item_id LIMIT 10001",
                (feed.id, subject, now, now),
            ).fetchall()
            value["items"] = [json.loads(r["payload"]) for r in records[:10000]]
            status = store.db.execute(
                "SELECT complete FROM context_feed_status WHERE source=? AND subject=?",
                (feed.id, subject),
            ).fetchone()
            value["complete"] = "yes" if status and status[0] and len(records) <= 10000 else "no"
        if not include_items:
            if store.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='context_feed_status'"
            ).fetchone():
                status = store.db.execute(
                    "SELECT complete FROM context_feed_status WHERE source=? AND subject=? AND expires_at>?",
                    (feed.id, "unknown" if feed.household else setup["profile"], now),
                ).fetchone()
                value["complete"] = "yes" if status and status[0] else "no"
            result.append(
                {
                    "source": feed.id,
                    **coverage_scope(feed, cfg),
                    "complete": value["complete"] == "yes",
                    "retrieval_tool": "get_context_feed",
                    "checked_at": row["observed_at"],
                    "items": [],
                }
            )
            continue
        result.append(
            {
                "source": feed.id,
                **coverage_scope(feed, cfg),
                "complete": value["complete"] == "yes",
                "items": [
                    item
                    for item in value["items"]
                    if feed.id != "transit" or item.get("end_at", now + 1) > now
                ],
            }
        )
        if len(result) >= limit:
            break
    return result


class Feeds:
    def __init__(self, folder, *, clock=time.time, reader=None):
        self.folder, self.clock, self.reader = Path(folder), clock, reader
        self.health, self.next_poll = {}, {}
        self.lock = threading.Lock()
        from .trakt_auth import TraktAuth

        self.trakt_auth = TraktAuth(self)

    def store(self):
        return closing(Store(self.folder, clock=self.clock))

    def snapshot(self):
        with self.store() as store:
            setup = preference(store, SYSTEM, KEY, {})
            feeds = []
            for feed in FEEDS.values():
                cfg = {**default(feed), **preference(store, SYSTEM, PREFIX + feed.id, {})}
                status = (
                    "disabled"
                    if not cfg["enabled"]
                    else "waiting"
                    if permitted(setup, feed)
                    else "paused_or_not_consented"
                )
                feeds.append(
                    dict(
                        id=feed.id,
                        label=feed.label,
                        transport=feed.transport,
                        instructions=feed.instructions,
                        options=list(TRAKT_OPTIONS) if feed.id == "watch_history" else [],
                        fields=[
                            {"key": k, "label": label, "domain": domain}
                            for k, label, domain in feed.fields
                        ],
                        config=cfg,
                        status=self.health.get(feed.id, {}).get("state", status)
                        if permitted(setup, feed) and cfg["enabled"]
                        else status,
                        consented=feed.id in setup.get("sources", []),
                        interval_seconds=feed.interval,
                    )
                )
            connections = []
            for name in ("ha", "trakt"):
                cfg = preference(store, SYSTEM, "feed_connection." + name, {})
                connections.append(
                    {
                        "transport": name,
                        "url": cfg.get("url", ""),
                        "client_id": cfg.get("client_id", ""),
                        "has_token": bool(cfg.get("token")),
                    }
                )
            return {
                "feeds": feeds,
                "connections": connections,
                "context": context(store),
                "delivery_enabled": False,
                "storage_policy": preference(
                    store, SYSTEM, "feed.storage_policy", {"signal_window_minutes": 15}
                ),
            }

    def storage_policy(self, data):
        if (
            not isinstance(data, dict)
            or set(data) != {"signal_window_minutes"}
            or type(data["signal_window_minutes"]) is not int
            or not 1 <= data["signal_window_minutes"] <= 60
        ):
            raise ValueError("Signal window must be 1–60 minutes")
        with self.store() as store, store.db:
            if not preference(store, SYSTEM, KEY, {}).get("profile"):
                raise ValueError("Save private setup first")
            store.db.execute(
                "INSERT OR REPLACE INTO preferences VALUES (?,?,?,?)",
                (SYSTEM, "feed.storage_policy", encode(data), self.clock()),
            )
        return self.snapshot()

    def retrieve(self, source, *, query="", offset=0, limit=20, view="current"):
        from .context_records import query as read_records

        if source not in (*FEEDS, "calendar") or not isinstance(query, str) or len(query) > 200:
            raise ValueError("Choose a registered source and bounded search")
        if (
            type(offset) is not int
            or not 0 <= offset <= 100000
            or type(limit) is not int
            or not 1 <= limit <= 50
        ):
            raise ValueError("Use a bounded retrieval page")
        if view not in ("current", "changes", "aggregates"):
            raise ValueError("Choose a supported retrieval view")
        with self.store() as store:
            setup = preference(store, SYSTEM, KEY, {})
            if source == "calendar":
                if (
                    not setup.get("profile")
                    or setup.get("paused")
                    or setup.get("guest")
                    or source not in setup.get("sources", [])
                ):
                    return {"items": [], "state": "paused_or_not_consented", "next_offset": None}
                return read_records(
                    store,
                    source,
                    setup["profile"],
                    text=query,
                    offset=offset,
                    limit=limit,
                    view=view,
                )
            feed = FEEDS[source]
            cfg = {**default(feed), **preference(store, SYSTEM, PREFIX + source, {})}
            if not cfg["enabled"] or not permitted(setup, feed):
                return {"items": [], "state": "paused_or_not_consented", "next_offset": None}
            result = read_records(
                store,
                source,
                "unknown" if feed.household else setup["profile"],
                text=query,
                offset=offset,
                limit=limit,
                view=view,
            )
            return {**result, **coverage_scope(feed, cfg)}

    def inventory(self):
        from .ha_inventory import preview

        with self.store() as store:
            connection = preference(store, SYSTEM, "feed_connection.ha", {})
        return preview(connection)

    def configure(self, data):
        if not isinstance(data, dict) or set(data) != {"id", "config"} or data["id"] not in FEEDS:
            raise ValueError("Choose a registered feed")
        feed = FEEDS[data["id"]]
        cfg = validate_config(feed, data["config"])
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = preference(store, SYSTEM, KEY, {})
            if not setup.get("profile"):
                raise ValueError("Save private setup first")
            previous_cfg = {**default(feed), **preference(store, SYSTEM, PREFIX + feed.id, {})}
            removed = any(set(previous_cfg[key]) - set(cfg[key]) for key, _, _ in feed.fields)
            if feed.id == "watch_history":
                removed = (
                    bool(set(previous_cfg["watched_lists"]) - set(cfg["watched_lists"]))
                    or cfg["history_days"] < previous_cfg["history_days"]
                )
            # UI explicitly labels enabling as consent for this feed. Do not resume
            # global pause/guest mode, change health permissions or other sources.
            if cfg["enabled"] and feed.id not in setup["sources"]:
                setup["sources"] = sorted([*setup["sources"], feed.id])
                store.db.execute(
                    "UPDATE preferences SET value=?,updated_at=? WHERE subject=? AND key=?",
                    (encode(setup), self.clock(), SYSTEM, KEY),
                )
            store.db.execute(
                "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) DO UPDATE "
                "SET value=excluded.value,updated_at=excluded.updated_at",
                (SYSTEM, PREFIX + feed.id, json.dumps(cfg, sort_keys=True), self.clock()),
            )
            store.db.execute(
                "INSERT OR REPLACE INTO preferences VALUES (?,?,?,?)",
                (SYSTEM, "feed_revision." + feed.id, encode(uuid.uuid4().hex), self.clock()),
            )
            from .context_records import clear

            if removed:
                clear(store.db, source=feed.id)
            elif (
                cfg != previous_cfg
                and store.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='context_feed_status'"
                ).fetchone()
            ):
                # A wider scope needs a new completeness check, not destruction of retained observations.
                store.db.execute(
                    "UPDATE context_feed_status SET complete=0 WHERE source=?", (feed.id,)
                )
            # Bindings changed: invalidate old snapshots and derived evaluations.
            store.db.execute(
                "DELETE FROM events WHERE source=? AND kind='feed_snapshot'", (feed.id,)
            )
            if store.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='shadow_decisions'"
            ).fetchone():
                store.db.execute("DELETE FROM shadow_decisions")
        self.next_poll.pop(feed.id, None)
        self.health.pop(feed.id, None)
        return self.snapshot()

    def connect(self, data):
        """Owner-only, write-only credentials; GET/export never returns secrets."""
        if not isinstance(data, dict) or data.get("transport") not in ("ha", "trakt"):
            raise ValueError("Choose a feed connection")
        name = data["transport"]
        if name == "trakt":
            with self.trakt_auth.lock:
                self.trakt_auth.pending = None
        if data == {"transport": name, "disconnect": True}:
            with self.store() as store, store.db:
                store.db.execute("BEGIN IMMEDIATE")
                store.db.execute(
                    "DELETE FROM preferences WHERE subject=? AND key=?",
                    (SYSTEM, "feed_connection." + name),
                )
                store.db.execute(
                    "INSERT OR REPLACE INTO preferences VALUES (?,?,?,?)",
                    (
                        SYSTEM,
                        "feed_connection_revision." + name,
                        encode(uuid.uuid4().hex),
                        self.clock(),
                    ),
                )
                for feed in FEEDS.values():
                    if feed.transport != name:
                        continue
                    cfg = {**default(feed), **preference(store, SYSTEM, PREFIX + feed.id, {})}
                    cfg["enabled"] = False
                    store.db.execute(
                        "INSERT OR REPLACE INTO preferences VALUES (?,?,?,?)",
                        (SYSTEM, PREFIX + feed.id, json.dumps(cfg, sort_keys=True), self.clock()),
                    )
                    store.db.execute(
                        "DELETE FROM events WHERE source=? AND kind='feed_snapshot'", (feed.id,)
                    )
                    from .context_records import clear

                    clear(store.db, source=feed.id)
                    self.next_poll.pop(feed.id, None)
                    self.health.pop(feed.id, None)
            return self.snapshot()
        fields = (
            {"transport", "token", "url"} if name == "ha" else {"transport", "token", "client_id"}
        )
        if set(data) != fields or any(
            not isinstance(v, str) or len(v) > 4000 for v in data.values()
        ):
            raise ValueError("Use bounded connection fields")
        if any("\n" in v or "\r" in v for v in data.values()):
            raise ValueError("Invalid connection text")
        if name == "ha":
            parts = urlsplit(data["url"])
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.query
                or parts.fragment
                or parts.path not in ("", "/")
            ):
                raise ValueError("Use a Home Assistant origin")
        elif not data["client_id"].strip():
            raise ValueError("Supply a Trakt client ID")
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            if not preference(store, SYSTEM, KEY, {}).get("profile"):
                raise ValueError("Save private setup first")
            old = preference(store, SYSTEM, "feed_connection." + name, {})
            cfg = {k: v.strip() for k, v in data.items() if k != "transport"}
            cfg["token"] = cfg["token"] or old.get("token", "")
            if not cfg["token"]:
                raise ValueError("Supply a private token")
            if (
                name == "trakt"
                and cfg["client_id"] == old.get("client_id")
                and cfg["token"] == old.get("token")
            ):
                # Saving visible settings must not discard private OAuth refresh metadata.
                cfg = {**old, **cfg}
            store.db.execute(
                "INSERT OR REPLACE INTO preferences VALUES (?,?,?,?)",
                (SYSTEM, "feed_connection." + name, encode(cfg), self.clock()),
            )
            if cfg != old:
                store.db.execute(
                    "INSERT OR REPLACE INTO preferences VALUES (?,?,?,?)",
                    (
                        SYSTEM,
                        "feed_connection_revision." + name,
                        encode(uuid.uuid4().hex),
                        self.clock(),
                    ),
                )
            for feed in FEEDS.values():
                if feed.transport == name and cfg != old:
                    store.db.execute(
                        "DELETE FROM events WHERE source=? AND kind='feed_snapshot'", (feed.id,)
                    )
                    from .context_records import clear

                    clear(store.db, source=feed.id)
                    self.next_poll.pop(feed.id, None)
                    self.health.pop(feed.id, None)
        return self.snapshot()

    def check(self, data):
        if not isinstance(data, dict) or set(data) != {"id"} or data["id"] not in FEEDS:
            raise ValueError("Choose a feed")
        feed = FEEDS[data["id"]]
        with self.store() as store:
            setup = preference(store, SYSTEM, KEY, {})
            cfg = {**default(feed), **preference(store, SYSTEM, PREFIX + feed.id, {})}
        if not cfg["enabled"] or not permitted(setup, feed):
            raise ValueError("Save consent and enable this feed before reading")
        self.next_poll.pop(feed.id, None)
        self.tick(only=feed.id)
        return self.snapshot()

    def _read_allowed(self, feed, setup, cfg, connection, revision, connection_revision):
        with self.store() as store:
            return (
                preference(store, SYSTEM, KEY, {}) == setup
                and {**default(feed), **preference(store, SYSTEM, PREFIX + feed.id, {})} == cfg
                and preference(store, SYSTEM, "feed_revision." + feed.id) == revision
                and preference(store, SYSTEM, "feed_connection_revision." + feed.transport)
                == connection_revision
                and preference(store, SYSTEM, "feed_connection." + feed.transport, {}) == connection
            )

    def tick(self, *, only=None):
        if not self.lock.acquire(blocking=False):
            return
        try:
            for feed in FEEDS.values():
                if only is not None and feed.id != only:
                    continue
                now = self.clock()
                if self.next_poll.get(feed.id, 0) > now:
                    continue
                with self.store() as store:
                    setup = preference(store, SYSTEM, KEY, {})
                    cfg = {**default(feed), **preference(store, SYSTEM, PREFIX + feed.id, {})}
                    revision = preference(store, SYSTEM, "feed_revision." + feed.id)
                    connection = preference(store, SYSTEM, "feed_connection." + feed.transport, {})
                    connection_revision = preference(
                        store, SYSTEM, "feed_connection_revision." + feed.transport
                    )
                if not cfg["enabled"] or not permitted(setup, feed):
                    continue  # No network reads without current consent.
                self.next_poll[feed.id] = now + feed.interval
                try:
                    if feed.transport == "trakt":
                        connection = self.trakt_auth.refresh(connection)
                    items, complete = (
                        self.reader(feed, cfg, now)
                        if self.reader
                        else fetch(
                            feed,
                            cfg,
                            now,
                            connection,
                            allowed=lambda: self._read_allowed(
                                feed, setup, cfg, connection, revision, connection_revision
                            ),
                        )
                    )
                    if not isinstance(items, list) or type(complete) is not bool:
                        raise ValueError("Invalid adapter result")
                    for start in range(0, len(items), 20):
                        validate_snapshot(
                            dict(
                                provider=feed.id,
                                items=items[start : start + 20],
                                complete="no",
                                valid_until_at=now + feed.freshness,
                            )
                        )
                    full_items, source_complete = items, complete
                    # Prompt/legacy previews are bounded; authoritative item storage is not truncated.
                    complete = complete and len(items) <= 20
                    payload = dict(
                        provider=feed.id,
                        items=items[:20],
                        complete="yes" if complete else "no",
                        valid_until_at=now + feed.freshness,
                    )
                    while len(json.dumps(payload).encode()) > 3500 and payload["items"]:
                        payload["items"].pop()
                        payload["complete"] = "no"
                    validate_snapshot(payload)
                    with self.store() as store, store.db:
                        store.db.execute("BEGIN IMMEDIATE")
                        # Forget/revocation/pause/rebinding during HTTP discards result.
                        if (
                            preference(store, SYSTEM, KEY, {}) != setup
                            or {**default(feed), **preference(store, SYSTEM, PREFIX + feed.id, {})}
                            != cfg
                            or preference(store, SYSTEM, "feed_revision." + feed.id) != revision
                            or preference(
                                store, SYSTEM, "feed_connection_revision." + feed.transport
                            )
                            != connection_revision
                            or preference(store, SYSTEM, "feed_connection." + feed.transport, {})
                            != connection
                        ):
                            self.health[feed.id] = {"state": "context_changed"}
                            continue
                        from .context_records import ingest

                        store.retention = setup["retention_days"] * 86400
                        ingest(
                            store,
                            feed.id,
                            "unknown" if feed.household else setup["profile"],
                            full_items,
                            complete=source_complete,
                            valid_until=now + feed.freshness,
                            noisy=feed.id in ("device_activity", "appliances", "room_activity"),
                            window_seconds=60
                            * preference(
                                store, SYSTEM, "feed.storage_policy", {"signal_window_minutes": 15}
                            )["signal_window_minutes"],
                        )
                        # Keep one compatibility preview per source; history lives in changes/buckets.
                        store.db.execute(
                            "DELETE FROM events WHERE source=? AND kind='feed_snapshot'", (feed.id,)
                        )
                        store.sources = frozenset([feed.id])
                        store.retention = setup["retention_days"] * 86400
                        store.observe(
                            source=feed.id,
                            external_id=digest([payload, int(now // feed.interval)]),
                            subject="unknown" if feed.household else setup["profile"],
                            kind="feed_snapshot",
                            payload=payload,
                        )
                    self.health[feed.id] = {
                        "state": "connected" if source_complete else "connected_partial"
                    }
                except Exception as exc:
                    from .trakt_history import CollectionCancelled

                    if isinstance(exc, CollectionCancelled):
                        self.health[feed.id] = {"state": "context_changed"}
                        continue
                    # Exception text can include tokens, URLs or provider bodies.
                    self.health[feed.id] = {"state": "unavailable_check_setup"}
                    if feed.transport == "ha":
                        # Local HA may still be starting; do not wait a full feed interval.
                        self.next_poll[feed.id] = now + min(feed.interval, 30)
        finally:
            self.lock.release()

    def run(self, stop):
        while not stop.is_set():
            try:
                self.tick()
            except Exception:
                pass  # Keep provider failures isolated from the controller.
            stop.wait(15)


def room_media_busy(store):
    """Additional fail-closed speech gate for consented selected room players."""
    setup = preference(store, SYSTEM, KEY, {})
    cfg = preference(store, SYSTEM, PREFIX + "room_activity", {})
    if (
        not permitted(setup, FEEDS["room_activity"])
        or not cfg.get("enabled")
        or not cfg.get("players")
    ):
        return False
    snapshot = next((v for v in context(store, full=True) if v["source"] == "room_activity"), None)
    if not snapshot or snapshot["complete"] is not True:
        return True
    players = [v for v in snapshot["items"] if v.get("category") == "media_player"]
    return len(players) != len(cfg["players"]) or any(
        p["state"] not in ("off", "standby", "idle", "paused") for p in players
    )

"""Private loss-aware compaction for normalized, already-consented source records.

Stable source IDs are authoritative; text similarity never merges records.
Noisy signals retain current state and interval statistics, not duplicate bodies.
"""

import json
import math
from .amadeus import encode


def ensure(db):
    db.execute("""CREATE TABLE IF NOT EXISTS context_records (
        source TEXT, subject TEXT, item_id TEXT, payload TEXT NOT NULL,
        first_seen REAL, last_seen REAL, changed_at REAL, expires_at REAL,
        valid_until REAL, reports INTEGER NOT NULL,
        PRIMARY KEY(source,subject,item_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS context_changes (
        source TEXT, subject TEXT, item_id TEXT, observed_at REAL, kind TEXT,
        payload TEXT, expires_at REAL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS context_signal_buckets (
        source TEXT, subject TEXT, item_id TEXT, bucket REAL, window_seconds INTEGER,
        reports INTEGER, transitions INTEGER, first_payload TEXT, last_payload TEXT,
        minimum REAL, maximum REAL, total REAL, numeric_count INTEGER, expires_at REAL,
        PRIMARY KEY(source,subject,item_id,bucket,window_seconds))""")
    db.execute("""CREATE TABLE IF NOT EXISTS context_feed_status (
        source TEXT, subject TEXT, checked_at REAL, complete INTEGER, expires_at REAL,
        PRIMARY KEY(source,subject))""")
    db.execute("CREATE INDEX IF NOT EXISTS context_record_expiry ON context_records(expires_at)")


def clear(db, source=None, subject=None):
    where, values = [], []
    for key, value in (("source", source), ("subject", subject)):
        if value is not None:
            where.append(key + "=?")
            values.append(value)
    for table in (
        "context_records",
        "context_changes",
        "context_signal_buckets",
        "context_feed_status",
    ):
        if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            db.execute(
                "DELETE FROM " + table + (" WHERE " + " AND ".join(where) if where else ""), values
            )


def prune(db, now):
    for table in (
        "context_records",
        "context_changes",
        "context_signal_buckets",
        "context_feed_status",
    ):
        if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            db.execute("DELETE FROM " + table + " WHERE expires_at<=?", (now,))


def migrate_legacy(store, source, subject):
    """Preserve distinct retained versions before retiring repeated legacy snapshots."""
    if store.db.execute(
        "SELECT 1 FROM context_feed_status WHERE source=? AND subject=?", (source, subject)
    ).fetchone():
        return
    previous = {}
    for row in store.db.execute(
        "SELECT * FROM events WHERE source=? AND subject=? AND kind IN ('feed_snapshot','calendar') AND expires_at>? ORDER BY observed_at,rowid",
        (source, subject, store.clock()),
    ):
        payload = json.loads(row["payload"])
        items = (
            payload.get("items", [])
            if row["kind"] == "feed_snapshot"
            else [
                {
                    "id": payload["event_id"],
                    **{k: v for k, v in payload.items() if k != "snapshot_id"},
                }
            ]
        )
        for item in items:
            raw = encode(item)
            identity = item["id"]
            if previous.get(identity) == raw:
                continue
            previous[identity] = raw
            store.db.execute(
                "INSERT INTO context_changes VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    subject,
                    identity,
                    row["observed_at"],
                    "legacy_observed",
                    raw,
                    row["expires_at"],
                ),
            )


def ingest(
    store, source, subject, items, *, complete, valid_until, noisy=False, window_seconds=900
):
    """Caller holds transaction and rechecks consent/config after source reads."""
    ensure(store.db)
    migrate_legacy(store, source, subject)
    now, expiry = store.clock(), store.clock() + store.retention
    store.db.execute(
        "INSERT OR REPLACE INTO context_feed_status VALUES (?,?,?,?,?)",
        (source, subject, now, int(complete), expiry),
    )
    seen = {}
    for item in items:
        identity, raw = item["id"], encode(item)
        if identity in seen:
            if seen[identity] != raw:
                raise ValueError("Conflicting stable item ID within a source response")
            continue
        seen[identity] = raw
        old = store.db.execute(
            "SELECT * FROM context_records WHERE source=? AND subject=? AND item_id=?",
            (source, subject, identity),
        ).fetchone()
        changed = old is None or old["payload"] != raw
        if noisy:
            bucket = int(now // window_seconds) * window_seconds
            try:
                numeric = float(item.get("state", ""))
                if not math.isfinite(numeric) or abs(numeric) > 1e100:
                    numeric = None
            except (ValueError, TypeError):
                numeric = None
            store.db.execute(
                """INSERT INTO context_signal_buckets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source,subject,item_id,bucket,window_seconds) DO UPDATE SET
                reports=reports+1, transitions=transitions+excluded.transitions,
                last_payload=excluded.last_payload,
                minimum=CASE WHEN excluded.minimum IS NULL THEN minimum WHEN minimum IS NULL THEN excluded.minimum ELSE min(minimum,excluded.minimum) END,
                maximum=CASE WHEN excluded.maximum IS NULL THEN maximum WHEN maximum IS NULL THEN excluded.maximum ELSE max(maximum,excluded.maximum) END,
                total=coalesce(total,0)+coalesce(excluded.total,0), numeric_count=numeric_count+excluded.numeric_count,
                expires_at=excluded.expires_at""",
                (
                    source,
                    subject,
                    identity + "|unit:" + item.get("unit", ""),
                    bucket,
                    window_seconds,
                    1,
                    int(old is not None and changed),
                    raw,
                    raw,
                    numeric,
                    numeric,
                    numeric,
                    int(numeric is not None),
                    expiry,
                ),
            )
            if changed and numeric is None:
                # Preserve discrete changes (including errors/completion); never average them away.
                store.db.execute(
                    "INSERT INTO context_changes VALUES (?,?,?,?,?,?,?)",
                    (
                        source,
                        subject,
                        identity,
                        now,
                        "first_observed" if old is None else "updated",
                        raw,
                        expiry,
                    ),
                )
        elif changed:
            store.db.execute(
                "INSERT INTO context_changes VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    subject,
                    identity,
                    now,
                    "first_observed" if old is None else "updated",
                    raw,
                    expiry,
                ),
            )
        store.db.execute(
            """INSERT INTO context_records VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source,subject,item_id) DO UPDATE SET payload=excluded.payload,
            last_seen=excluded.last_seen,changed_at=excluded.changed_at,
            expires_at=excluded.expires_at,valid_until=excluded.valid_until,reports=reports+1""",
            (
                source,
                subject,
                identity,
                raw,
                old["first_seen"] if old else now,
                now,
                now if changed else old["changed_at"],
                expiry,
                valid_until,
                1,
            ),
        )
    if complete:
        # Absence is inferred only from a complete authoritative snapshot, never a failed/partial read.
        for old in store.db.execute(
            "SELECT * FROM context_records WHERE source=? AND subject=?", (source, subject)
        ).fetchall():
            if old["item_id"] not in seen:
                store.db.execute(
                    "INSERT INTO context_changes VALUES (?,?,?,?,?,?,?)",
                    (source, subject, old["item_id"], now, "absent", old["payload"], expiry),
                )
                store.db.execute(
                    "DELETE FROM context_records WHERE source=? AND subject=? AND item_id=?",
                    (source, subject, old["item_id"]),
                )


def query(store, source, subject, *, text="", offset=0, limit=20, view="current"):
    ensure(store.db)
    if view != "current":
        if view not in ("changes", "aggregates"):
            raise ValueError("Choose current, changes or aggregates")
        table = "context_changes" if view == "changes" else "context_signal_buckets"
        stamp = "observed_at" if view == "changes" else "bucket"
        field = "payload" if view == "changes" else "last_payload"
        rows = store.db.execute(
            "SELECT * FROM "
            + table
            + " WHERE source=? AND subject=? AND expires_at>? AND (?='' OR instr(lower("
            + field
            + "),lower(?))>0) ORDER BY "
            + stamp
            + " DESC,rowid DESC LIMIT ? OFFSET ?",
            (source, subject, store.clock(), text, text, limit + 1, offset),
        ).fetchall()
        items = []
        for row in rows[:limit]:
            if view == "changes":
                value = json.loads(row["payload"])
                value["change"] = row["kind"]
            else:
                value = {
                    "unit": json.loads(row["last_payload"]).get("unit"),
                    "reports": row["reports"],
                    "transitions": row["transitions"],
                    "minimum": row["minimum"],
                    "maximum": row["maximum"],
                    "mean_observed": row["total"] / row["numeric_count"]
                    if row["numeric_count"]
                    else None,
                    "window_seconds": row["window_seconds"],
                    "first": json.loads(row["first_payload"]),
                    "last": json.loads(row["last_payload"]),
                }
            items.append({"value": value, "observed_at": row[stamp], "historical": True})
        return {
            "items": items,
            "view": view,
            "next_offset": offset + limit if len(rows) > limit else None,
            "scope": "Retained observations only, not a complete activity history. Aggregates are observed samples, not time-weighted averages.",
        }
    # instr provides literal matching; user text cannot change SQL or act as wildcard syntax.
    rows = store.db.execute(
        """SELECT * FROM context_records WHERE source=? AND subject=?
        AND expires_at>? AND (?='' OR instr(lower(payload),lower(?))>0)
        ORDER BY changed_at DESC,item_id LIMIT ? OFFSET ?""",
        (source, subject, store.clock(), text, text, limit + 1, offset),
    ).fetchall()
    status = store.db.execute(
        "SELECT * FROM context_feed_status WHERE source=? AND subject=?", (source, subject)
    ).fetchone()
    return {
        "source_snapshot_complete": bool(status["complete"]) if status else False,
        "checked_at": status["checked_at"] if status else None,
        "items": [
            {
                "value": json.loads(r["payload"]),
                "last_seen": r["last_seen"],
                "changed_at": r["changed_at"],
                "fresh": r["valid_until"] > store.clock(),
            }
            for r in rows[:limit]
        ],
        "next_offset": offset + limit if len(rows) > limit else None,
        "scope": "Selected source only; missing or stale records are not an all-clear.",
    }


def export(store, subject):
    """Owner export only, never prompt context; connection credentials are not included."""
    result = {}
    for table in (
        "context_records",
        "context_changes",
        "context_signal_buckets",
        "context_feed_status",
    ):
        if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            result[table] = []
            continue
        result[table] = []
        for row in store.db.execute(
            "SELECT * FROM " + table + " WHERE subject IN (?,'unknown') AND expires_at>?",
            (subject, store.clock()),
        ):
            value = dict(row)
            for key in ("payload", "first_payload", "last_payload"):
                if key in value:
                    value[key] = json.loads(value[key])
            result[table].append(value)
    return result

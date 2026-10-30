"""Read-only, consent-scoped household recap; observations are not an all-clear."""

from contextlib import closing
from datetime import datetime, timedelta
import json
import sqlite3
from pathlib import Path
import time
from zoneinfo import ZoneInfo
from .amadeus import Store
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY


def recap(folder, period="today", clock=time.time):
    if period not in ("today", "yesterday", "last_24_hours"):
        raise ValueError("Choose today, yesterday or last_24_hours")
    with closing(Store(folder, clock=clock)) as store:
        setup = preference(store, SYSTEM, KEY, {})
        if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
            return {
                "summary": "Household history is unavailable while private collection is paused or not configured.",
                "coverage": "unavailable",
                "observations": [],
                "period": period,
            }
        now = clock()
        zone = ZoneInfo(setup["timezone"])
        day = datetime.fromtimestamp(now, zone).replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = (
            (now - 86400, now)
            if period == "last_24_hours"
            else (
                ((day - timedelta(days=1)).timestamp(), day.timestamp())
                if period == "yesterday"
                else (day.timestamp(), now)
            )
        )
        # Count occurrence-keyed retained events independently of the small prose sample.
        # These are reported observations, never inferred physical deliveries/visitors.
        sources = setup.get("sources", [])
        event_counts = []
        if sources:
            groups = store.db.execute(
                "SELECT json_extract(payload,'$.provider') provider, json_extract(payload,'$.event') event, "
                "json_extract(payload,'$.provenance') provenance, count(*) count FROM events "
                "WHERE kind='household_event' AND observed_at>=? AND observed_at<? AND expires_at>? "
                "AND subject IN (?, 'unknown', 'household') AND source IN ("
                + ",".join("?" for _ in sources)
                + ") GROUP BY provider,event,provenance ORDER BY provider,event,provenance LIMIT 21",
                (start, end, now, setup["profile"], *sources),
            ).fetchall()
            event_counts = [dict(r) for r in groups[:20]]
        else:
            groups = []
        rows = store.db.execute(
            "SELECT source,kind,payload,observed_at FROM events WHERE observed_at>=? AND observed_at<? "
            "AND expires_at>? AND subject IN (?, 'unknown', 'household') "
            "AND kind IN ('door','presence','tv_state','media','feed_snapshot','household_event') "
            "ORDER BY observed_at DESC,rowid DESC LIMIT 200",
            (start, end, now, setup["profile"]),
        ).fetchall()
        observations, seen = [], set()
        for row in rows:
            if row["source"] not in setup["sources"]:
                continue
            payload = json.loads(row["payload"])
            kind = row["kind"]
            if kind == "feed_snapshot":
                if payload.get("provider") != "appliances":
                    continue
                cfg = preference(store, SYSTEM, "feed.appliances", {})
                if not cfg.get("enabled"):
                    continue
                for item in payload["items"][:3]:
                    key = ("appliance", item["id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    observations.append(
                        {
                            "kind": "appliance",
                            "text": item["label"] + ": " + item["state"],
                            "observed_at": row["observed_at"],
                        }
                    )
                continue
            if kind == "household_event":
                observations.append(
                    {
                        "kind": kind,
                        "text": payload["detail"] + " (" + payload["provenance"] + ")",
                        "observed_at": row["observed_at"],
                    }
                )
                continue
            key = (kind, payload.get("device_id", payload.get("app", "")))
            if key in seen:
                continue
            seen.add(key)
            if kind == "door":
                detail = "Door sensor reported " + payload["state"]
            elif kind == "presence":
                detail = "Household presence estimate was " + payload["state"]
            elif kind == "tv_state":
                detail = "A TV reported " + payload["state"]
            else:
                detail = payload.get("app", "Media") + " reported " + payload["state"].lower()
                if payload.get("title"):
                    detail += ": " + payload["title"]
            observations.append({"kind": kind, "text": detail, "observed_at": row["observed_at"]})
        inbox = Path(folder).parent / "notifications.sqlite3"
        if inbox.exists():
            with closing(
                sqlite3.connect(inbox.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
            ) as db:
                notices = db.execute(
                    "SELECT payload,created FROM notifications WHERE created>=? AND created<? "
                    "AND json_extract(payload, '$.source') IN "
                    "('ring','home-assistant','home_assistant','homeassistant','thinq','home','door','alexa') "
                    "ORDER BY created DESC LIMIT 30",
                    (start, end),
                ).fetchall()
            alerts = []
            for raw, created in notices:
                notice = json.loads(raw)
                if notice.get("source") in (
                    "ring",
                    "home-assistant",
                    "home_assistant",
                    "homeassistant",
                    "thinq",
                    "home",
                    "door",
                    "alexa",
                ):
                    alerts.append(
                        {
                            "kind": "notification",
                            "text": str(notice.get("title", "Household alert"))[:100],
                            "observed_at": created,
                        }
                    )
            observations = alerts[:3] + observations
        # Event history takes precedence over routine last-state readings.
        observations.sort(
            key=lambda o: (o["kind"] not in ("household_event", "notification"), -o["observed_at"])
        )
        label = period.replace("_", " ")
        facts = [
            o["text"][:100]
            + " at "
            + datetime.fromtimestamp(o["observed_at"], zone).strftime("%H:%M")
            for o in observations[:3]
        ]
        summary = (
            "From "
            + label
            + "'s connected records: "
            + "; ".join(facts)
            + ". This is partial history, not a complete house check."
            if facts
            else "I don't have enough connected household history for "
            + label
            + " to say what happened. Missing records don't mean nothing happened."
        )
        return {
            "summary": summary[:550],
            "period": period,
            "coverage": "partial",
            "start_at": start,
            "end_at": end,
            "observations": observations[:12],
            "recorded_event_counts": event_counts,
            "event_categories_truncated": len(groups) > 20,
            "count_scope": "Retained consented event records in this period only. User-confirmed delivery records are distinct from Ring motion/doorbell detections; no complete delivery total is established.",
        }

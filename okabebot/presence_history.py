"""Bounded selected-source presence reports, never proof of physical departure."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .amadeus_feeds import Feeds
from .amadeus_onboarding import SYSTEM, KEY
from .amadeus_habits import preference


def timeline(folder, period="today", *, clock=None):
    import time

    clock = clock or time.time
    if period not in ("today", "this_morning", "yesterday", "last_24_hours"):
        raise ValueError("Choose a supported presence period")
    feeds = Feeds(folder, clock=clock)
    with feeds.store() as store:
        setup = preference(store, SYSTEM, KEY, {})
    now = clock()
    zone = ZoneInfo(setup.get("timezone", "UTC"))
    day = datetime.fromtimestamp(now, zone).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (
        now - 86400
        if period == "last_24_hours"
        else (day - timedelta(days=period == "yesterday")).timestamp()
    )
    end = (
        day.timestamp()
        if period == "yesterday"
        else min(now, day.replace(hour=12).timestamp())
        if period == "this_morning"
        else now
    )
    records, offset, checked, complete = [], 0, None, False
    for _ in range(20):
        page = feeds.retrieve("presence_history", offset=offset, limit=50)
        if page.get("state"):
            return {"available": False, "state": page["state"], "transitions": [], "period": period}
        records.extend(r["value"] for r in page.get("items", []))
        checked, complete = page.get("checked_at"), page.get("source_snapshot_complete", False)
        offset = page.get("next_offset")
        if offset is None:
            break
    transitions, lanes, intervals, open_away, initial = [], {}, [], {}, {}
    for value in sorted(records, key=lambda r: (r.get("reported_at", 0), r.get("id", ""))):
        at, lane = value.get("reported_at"), value.get("entity_key")
        if type(at) not in (int, float) or not lane or at >= end:
            continue
        previous = lanes.get(lane)
        state = value.get("state")
        lanes[lane] = state
        if at < start:
            initial[lane] = {
                "source_key": lane,
                "state": state,
                "source_type": value.get("source_type"),
                "observed_at": at,
                "label": value.get("label"),
            }
            continue
        if state == previous:
            continue
        row = {
            "at": datetime.fromtimestamp(at, zone).isoformat(),
            "state": state,
            "previous_state": previous,
            "source_type": value.get("source_type"),
            "source_key": lane,
            "label": value.get("label"),
            "observation": value.get("observation", "snapshot"),
        }
        transitions.append(row)
        if value.get("source_type") != "person":
            continue
        if state == "away" and row["observation"] == "change":
            open_away[lane] = at
        elif state != "away" and lane in open_away:
            began = open_away.pop(lane)
            intervals.append(
                {
                    "start_at": began,
                    "end_at": at,
                    "duration_seconds": at - began,
                    "ended_by": state,
                    "source_key": lane,
                }
            )
    for lane, began in open_away.items():
        intervals.append(
            {
                "start_at": began,
                "end_at": None,
                "duration_seconds": end - began,
                "ended_by": "window_end",
                "source_key": lane,
            }
        )
    return {
        "available": checked is not None,
        "period": period,
        "timezone": str(zone),
        "start_at": start,
        "end_at": end,
        "checked_at": checked,
        "fresh": checked is not None and 0 <= now - checked <= 180,
        "initial_states": list(initial.values()),
        "transitions": transitions[:100],
        "reported_away_intervals": intervals[:50],
        "truncated": offset is not None or len(transitions) > 100 or len(intervals) > 50,
        "source_snapshot_complete": complete,
        "scope": "Selected HA reports only. Snapshots are not transitions; unknown is not away. Zone counts do not identify people. Brief away reports may be noisy; no report proves physical departure or its exact time.",
    }

"""Read-only agenda projections from normalized calendar events."""

import datetime as dt
import time
from zoneinfo import ZoneInfo


def snapshot(state, timezone="local", now=None):
    now = time.time() if now is None else now
    date = dt.datetime.fromtimestamp(now, dt.timezone.utc).astimezone(
        None if timezone == "local" else ZoneInfo(timezone)
    )
    events = sorted(
        (e for e in state.get("calendar_upcoming", []) if e["start"] > now),
        key=lambda e: e["start"],
    )
    today = [
        e
        for e in events
        if dt.datetime.fromtimestamp(e["start"], date.tzinfo).date() == date.date()
    ]
    next_event = (
        dict(events[0], seconds_until=max(0, int(events[0]["start"] - now))) if events else None
    )
    checked = state.get("calendar_checked_at", 0)
    return dict(
        events=today[:20],
        next=next_event,
        timezone=timezone,
        checked_at=checked,
        stale=not checked or now - checked > 360,
        date=date.date().isoformat(),
    )


def publish(inbox, agenda, key=None):
    if agenda["stale"]:
        raise ValueError("Calendar is unavailable or stale; refresh before showing the agenda")
    entries = agenda["events"]
    body = "; ".join(
        dt.datetime.fromtimestamp(e["start"])
        .astimezone(None if agenda["timezone"] == "local" else ZoneInfo(agenda["timezone"]))
        .strftime("%H:%M")
        + " "
        + e["title"]
        for e in entries[:6]
    )
    if not body:
        body = "No more timed events today."
    return inbox.publish("calendar", "Today’s agenda", body[:500], "normal", key, audio="silent")


def schedule(context):
    at = context.settings.get("agenda_time", "")
    if not at:
        return
    agenda = snapshot(context.state, context.settings.get("agenda_timezone", "local"))
    date = dt.datetime.now(dt.timezone.utc).astimezone(
        None if agenda["timezone"] == "local" else ZoneInfo(agenda["timezone"])
    )
    hour, minute = map(int, at.split(":"))
    due = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if 0 <= (date - due).total_seconds() < 900 and not agenda["stale"]:
        publish(context.inbox, agenda, "agenda-" + agenda["date"])

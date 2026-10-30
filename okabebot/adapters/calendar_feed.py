"""ICS provider; credentials remain on the controller."""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import time
from urllib.request import urlopen


def load_calendar(settings):
    import icalendar

    source = settings["calendar"]
    if source.startswith("env:"):
        name = source[4:]
        source = os.environ.get(name, "")
        if not source:
            env_file = (
                Path(os.environ.get("OKABEBOT_CONFIG", "okabebot.local.json")).resolve().parent
                / ".env"
            )
            for line in env_file.read_text().splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == name:
                    source = shlex.split(value.strip())[0]
                    break
        if not source:
            raise ValueError("Calendar feed not configured")
    if source.startswith("https://"):
        with urlopen(source, timeout=15) as response:
            raw = response.read(2_000_001)
    else:
        raw = Path(source).expanduser().read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError("Calendar too large")
    return icalendar.Calendar.from_ical(raw)


def poll(context):
    import recurring_ical_events

    now = dt.datetime.fromtimestamp(time.time(), dt.timezone.utc)
    lead = context.settings["calendar_lead_minutes"]
    calendar = load_calendar(context.settings)
    recurring_uids = {
        str(e.get("UID", ""))
        for e in calendar.walk("VEVENT")
        if e.get("RRULE") or e.get("RDATE") or e.get("RECURRENCE-ID")
    }
    events = recurring_ical_events.of(calendar).between(now, now + dt.timedelta(days=2))
    scheduled = []
    upcoming = []
    intervals = []
    busy_complete = True
    for event in events:
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        start = event.decoded("DTSTART")
        all_day = isinstance(start, dt.date) and not isinstance(start, dt.datetime)
        if not isinstance(start, dt.date):
            busy_complete = False
            continue
        interval_start = dt.datetime.combine(start, dt.time()).astimezone() if all_day else start
        if interval_start.tzinfo is None:
            interval_start = interval_start.astimezone()
        end = event.decoded("DTEND", None)
        duration = event.decoded("DURATION", None)
        if end is None and isinstance(duration, dt.timedelta):
            end = start + duration
        if end is None and all_day:
            end = start + dt.timedelta(days=1)  # RFC5545 one-day default.
        if isinstance(end, dt.date) and not isinstance(end, dt.datetime):
            end = dt.datetime.combine(end, dt.time()).astimezone()
        if isinstance(end, dt.datetime) and end.tzinfo is None:
            end = end.astimezone()
        transparency = str(event.get("TRANSP", "OPAQUE")).upper()
        valid_interval = (
            isinstance(end, dt.datetime)
            and end > interval_start
            and transparency in ("OPAQUE", "TRANSPARENT")
        )
        uid = str(event.get("UID", ""))
        occurrence = str(event.get("RECURRENCE-ID", "")) if uid in recurring_uids else ""
        if not occurrence and event.get("RRULE"):
            occurrence = str(interval_start.timestamp())
        source_id = hashlib.sha256((uid + "|" + occurrence).encode()).hexdigest() if uid else ""
        if not valid_interval:
            busy_complete = False
        elif end > now and interval_start < now + dt.timedelta(days=2):
            intervals.append(
                dict(
                    source_id=source_id,
                    title=str(event.get("SUMMARY", "Calendar event"))[:100],
                    start=interval_start.timestamp(),
                    end=end.timestamp(),
                    busy=transparency != "TRANSPARENT",
                    all_day=all_day,
                )
            )
        if all_day:
            continue  # All-day events are not spoken appointments.
        if start.tzinfo is None:
            start = start.astimezone()
        due = start.timestamp() - lead * 60
        if start.timestamp() <= time.time():
            continue
        title = str(event.get("SUMMARY", "Calendar event"))[:100]
        upcoming.append(dict(title=title, start=start.timestamp(), source_id=source_id))
        identifier = (
            "feed-"
            + hashlib.sha256(
                (str(event.get("UID", title)) + "-" + str(start.timestamp())).encode()
            ).hexdigest()
        )
        item = context.inbox.publish(
            "calendar",
            title,
            "Starts at " + start.astimezone().strftime("%H:%M %Z"),
            "important",
            identifier,
            due,
            start.timestamp(),
            sender_id="".join(c for c in str(event.get("ORGANIZER", "")) if ord(c) >= 32).strip()[
                :160
            ]
            or None,
        )
        with context.inbox.connect() as db:
            updated = dict(
                item, title=title, body="Starts at " + start.astimezone().strftime("%H:%M %Z")
            )
            db.execute(
                "UPDATE notifications SET payload=?,due=?,expires=? WHERE id=? AND status='pending'",
                (json.dumps(updated), due, start.timestamp(), item["id"]),
            )
        scheduled.append(item["id"])
    with context.inbox.connect() as db:
        rows = db.execute(
            "SELECT id FROM notifications WHERE status='pending' AND dedupe LIKE 'calendar:feed-%'"
        ).fetchall()
        for (identifier,) in rows:
            if identifier not in scheduled:
                db.execute("UPDATE notifications SET status='cancelled' WHERE id=?", (identifier,))

    context.state["calendar_context"] = sorted(intervals, key=lambda e: e["start"])
    context.state["calendar_busy_complete"] = busy_complete and len(intervals) <= 200
    context.state["calendar_upcoming"] = sorted(upcoming, key=lambda e: e["start"])
    context.state["calendar_checked_at"] = time.time()
    from ..agenda import schedule

    schedule(context)

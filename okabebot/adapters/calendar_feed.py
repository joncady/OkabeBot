"""ICS provider; credentials remain on the controller."""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import time
from urllib.request import urlopen


def poll(context):
    import icalendar
    import recurring_ical_events

    source = context.settings["calendar"]
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
    now = dt.datetime.now(dt.timezone.utc)
    lead = context.settings["calendar_lead_minutes"]
    events = recurring_ical_events.of(icalendar.Calendar.from_ical(raw)).between(
        now, now + dt.timedelta(days=2)
    )
    scheduled = []
    for event in events:
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        start = event.decoded("DTSTART")
        if not isinstance(start, dt.datetime):
            continue  # All-day events are not spoken appointments.
        if start.tzinfo is None:
            start = start.astimezone()
        due = start.timestamp() - lead * 60
        if start.timestamp() <= time.time():
            continue
        title = str(event.get("SUMMARY", "Calendar event"))[:100]
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

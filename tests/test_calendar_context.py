"""Invented ICS context intervals without changing notification semantics."""

import datetime as dt
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import icalendar
from okabebot.adapters.calendar_feed import poll
from okabebot.notifications import Inbox


class CalendarContextTests(unittest.TestCase):
    def run_feed(self, body):
        now = dt.datetime(2030, 1, 7, 12, tzinfo=dt.timezone.utc)

        feed = icalendar.Calendar.from_ical(
            "BEGIN:VCALENDAR\nVERSION:2.0\n" + body + "\nEND:VCALENDAR"
        )
        with tempfile.TemporaryDirectory() as folder:
            ctx = SimpleNamespace(
                settings={"calendar_lead_minutes": 10}, state={}, inbox=Inbox(Path(folder))
            )
            with (
                patch("okabebot.adapters.calendar_feed.load_calendar", return_value=feed),
                patch("okabebot.adapters.calendar_feed.time.time", return_value=now.timestamp()),
                patch("okabebot.agenda.schedule"),
            ):
                poll(ctx)
            with ctx.inbox.connect() as db:
                notifications = db.execute("SELECT count(*) FROM notifications").fetchone()[0]
            return ctx.state, notifications

    def test_ongoing_all_day_and_transparent_intervals(self):
        state, notifications = self.run_feed("""BEGIN:VEVENT
UID:meeting
DTSTART:20300107T110000Z
DTEND:20300107T130000Z
SUMMARY:Invented ongoing appointment
END:VEVENT
BEGIN:VEVENT
UID:holiday
DTSTART;VALUE=DATE:20300107
SUMMARY:Invented holiday
END:VEVENT
BEGIN:VEVENT
UID:optional
DTSTART:20300107T140000Z
DTEND:20300107T150000Z
TRANSP:TRANSPARENT
SUMMARY:Optional reading
END:VEVENT
BEGIN:VEVENT
UID:cancelled
DTSTART:20300107T160000Z
DTEND:20300107T170000Z
STATUS:CANCELLED
SUMMARY:Cancelled
END:VEVENT""")
        intervals = {e["title"]: e for e in state["calendar_context"]}
        self.assertTrue(state["calendar_busy_complete"])
        self.assertIn("Invented ongoing appointment", intervals)
        self.assertTrue(intervals["Invented holiday"]["all_day"])
        self.assertFalse(intervals["Optional reading"]["busy"])
        self.assertNotIn("Cancelled", intervals)
        # Only future timed appointment remains in the legacy reminder stream.
        self.assertEqual([e["title"] for e in state["calendar_upcoming"]], ["Optional reading"])
        self.assertEqual(notifications, 1)

    def test_unknown_transparency_never_claims_complete_coverage(self):
        state, _ = self.run_feed("""BEGIN:VEVENT
UID:bad
DTSTART:20300107T140000Z
DTEND:20300107T150000Z
TRANSP:UNCERTAIN
SUMMARY:Unknown busy information
END:VEVENT""")
        self.assertFalse(state["calendar_busy_complete"])

    def test_uid_is_stable_across_rename_and_reschedule(self):
        first, _ = self.run_feed(
            "BEGIN:VEVENT\nUID:invented-stable\nDTSTART:20300107T140000Z\nDTEND:20300107T150000Z\nSUMMARY:Before\nEND:VEVENT"
        )
        second, _ = self.run_feed(
            "BEGIN:VEVENT\nUID:invented-stable\nDTSTART:20300107T160000Z\nDTEND:20300107T170000Z\nSUMMARY:After\nEND:VEVENT"
        )
        self.assertEqual(
            first["calendar_context"][0]["source_id"], second["calendar_context"][0]["source_id"]
        )

    def test_recurrences_stay_distinct_and_override_keeps_original_occurrence_id(self):
        body = "BEGIN:VEVENT\nUID:series\nDTSTART:20300107T140000Z\nDTEND:20300107T150000Z\nRRULE:FREQ=DAILY;COUNT=2\nSUMMARY:Invented series\nEND:VEVENT"
        before, _ = self.run_feed(body)
        after, _ = self.run_feed(
            body
            + "\nBEGIN:VEVENT\nUID:series\nRECURRENCE-ID:20300108T140000Z\nDTSTART:20300108T160000Z\nDTEND:20300108T170000Z\nSUMMARY:Rescheduled occurrence\nEND:VEVENT"
        )
        original = before["calendar_context"]
        changed = after["calendar_context"]
        self.assertEqual(len({r["source_id"] for r in original}), 2)
        self.assertEqual(original[1]["source_id"], changed[1]["source_id"])

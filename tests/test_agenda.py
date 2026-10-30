import datetime as dt
import tempfile
import unittest
from okabebot.agenda import snapshot, publish
from okabebot.notifications import Inbox


class AgendaTests(unittest.TestCase):
    def test_timezone_next_day_and_stale(self):
        now = dt.datetime(2026, 10, 25, 23, 30, tzinfo=dt.timezone.utc).timestamp()
        state = dict(
            calendar_checked_at=now,
            calendar_upcoming=[
                dict(title="Past", start=now - 60),
                dict(title="Soon", start=now + 600),
                dict(title="Tomorrow", start=now + 3600),
            ],
        )
        s = snapshot(state, "UTC", now)
        self.assertEqual([e["title"] for e in s["events"]], ["Soon"])
        self.assertEqual(s["next"]["seconds_until"], 600)
        self.assertFalse(s["stale"])
        self.assertTrue(snapshot(state, "UTC", now + 500)["stale"])

    def test_silent_summary_dedupe_and_stale_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            inbox = Inbox(folder)
            agenda = dict(events=[], stale=False, timezone="local")
            publish(inbox, agenda, "daily")
            publish(inbox, agenda, "daily")
            self.assertEqual(len(inbox.items()), 1)
            self.assertEqual(inbox.items()[0]["audio"], "silent")
            with self.assertRaises(ValueError):
                publish(inbox, dict(agenda, stale=True))

    def test_scheduled_local_morning_window_and_daily_dedupe(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from okabebot.agenda import schedule

        now = dt.datetime(2026, 10, 25, 15, 5, tzinfo=dt.timezone.utc)

        class Frozen(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return now.astimezone(tz)

        with tempfile.TemporaryDirectory() as folder:
            inbox = Inbox(folder)
            context = SimpleNamespace(
                inbox=inbox,
                settings=dict(agenda_time="08:00", agenda_timezone="America/Los_Angeles"),
                state=dict(calendar_checked_at=now.timestamp(), calendar_upcoming=[]),
            )
            with (
                patch("okabebot.agenda.dt.datetime", Frozen),
                patch("okabebot.agenda.time.time", side_effect=lambda: now.timestamp()),
            ):
                schedule(context)
                schedule(context)
                self.assertEqual(len(inbox.items()), 1)
                now += dt.timedelta(days=1, minutes=25)
                context.state["calendar_checked_at"] = now.timestamp()
                schedule(context)
                self.assertEqual(len(inbox.items()), 1)


class CalendarToolTests(unittest.TestCase):
    def test_tomorrow_boundary_stale_and_missing(self):
        import json
        from pathlib import Path
        from okabebot.agenda import read_calendar

        now = dt.datetime(2026, 10, 26, 23, 30, tzinfo=dt.timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(read_calendar(folder, "UTC", now=now)["available"])
            Path(folder, "notification-sources.json").write_text(
                json.dumps(
                    dict(
                        calendar_checked_at=now,
                        calendar_upcoming=[
                            dict(title="Today", start=now + 60),
                            dict(title="Tomorrow", start=now + 3600),
                        ],
                    )
                )
            )
            result = read_calendar(folder, "UTC", "tomorrow", now)
            self.assertEqual(result["date"], "2026-10-27")
            self.assertEqual([e["title"] for e in result["events"]], ["Tomorrow"])
            stale = read_calendar(folder, "UTC", "tomorrow", now + 400)
            self.assertFalse(stale["available"])
            self.assertEqual(stale["events"], [])
            with self.assertRaises(ValueError):
                read_calendar(folder, "UTC", "yesterday", now)


class CalendarRangeTests(unittest.TestCase):
    def test_arbitrary_range_recurrence_all_day_and_cancelled(self):
        from unittest.mock import patch
        import icalendar
        from okabebot.agenda import query_calendar

        feed = icalendar.Calendar.from_ical("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:daily
DTSTART:20270101T120000Z
RRULE:FREQ=DAILY;COUNT=3
SUMMARY:Daily
END:VEVENT
BEGIN:VEVENT
UID:day
DTSTART;VALUE=DATE:20270102
SUMMARY:Holiday
END:VEVENT
BEGIN:VEVENT
UID:cancelled
DTSTART:20270102T130000Z
STATUS:CANCELLED
SUMMARY:Cancelled
END:VEVENT
END:VCALENDAR""")
        with patch("okabebot.adapters.calendar_feed.load_calendar", return_value=feed):
            result = query_calendar({"agenda_timezone": "UTC"}, "2027-01-01", "2027-01-03")
        self.assertTrue(result["available"])
        self.assertEqual(len(result["events"]), 3)
        self.assertEqual(sum(e["all_day"] for e in result["events"]), 1)
        with self.assertRaises(ValueError):
            query_calendar({"agenda_timezone": "UTC"}, "2027-01-03", "2027-01-01")

    def test_error_does_not_leak_feed_credentials(self):
        from unittest.mock import patch
        from okabebot.agenda import query_calendar

        with patch(
            "okabebot.adapters.calendar_feed.load_calendar", side_effect=ValueError("SECRET")
        ):
            result = query_calendar({"agenda_timezone": "UTC"}, "2027-01-01", "2027-01-03")
        self.assertFalse(result["available"])
        self.assertNotIn("SECRET", str(result))

    def test_conversation_week_is_calendar_week_and_today_is_full_day(self):
        from okabebot.agenda import conversation_range

        now = dt.datetime(2030, 5, 15, 15, tzinfo=dt.timezone.utc).timestamp()
        self.assertEqual(
            conversation_range("this week", now, "UTC"),
            {"start_date": "2030-05-13", "end_date": "2030-05-20"},
        )
        self.assertEqual(
            conversation_range("today", now, "UTC"),
            {"start_date": "2030-05-15", "end_date": "2030-05-16"},
        )
        self.assertEqual(
            conversation_range("next week", now, "UTC"),
            {"start_date": "2030-05-20", "end_date": "2030-05-27"},
        )

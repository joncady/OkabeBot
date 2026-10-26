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

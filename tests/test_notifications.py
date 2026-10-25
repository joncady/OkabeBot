import datetime as dt
import tempfile
import time
import unittest
from pathlib import Path
from okabebot.notifications import Inbox
from okabebot.sources import Sources
from pi import scene


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.inbox = Inbox(self.tmp.name)

    def test_priority_dedupe_and_expiry(self):
        now = time.time()
        a = self.inbox.publish("system", "normal", dedupe_key="once")
        self.assertEqual(a, self.inbox.publish("system", "normal", dedupe_key="once"))
        b = self.inbox.publish("system", "urgent", priority="urgent")
        self.inbox.publish("system", "old", due_at=now - 10, expires_at=now - 1)
        self.assertEqual(b["id"], self.inbox.claim()["id"])
        self.assertEqual(a["id"], self.inbox.claim()["id"])
        self.assertIsNone(self.inbox.claim())
        self.assertIn("expired", [n["status"] for n in self.inbox.items()])

    def test_second_client_does_not_reset_delivery_and_restart_does_not_replay(self):
        self.inbox.publish("system", "One")
        self.inbox.claim()
        other = Inbox(self.tmp.name)
        self.assertEqual("delivering", other.items()[0]["status"])
        other.recover()
        self.assertEqual("uncertain", other.items()[0]["status"])
        self.assertIsNone(other.claim())

    def test_calendar_recurrence_and_cancellation(self):
        try:
            import icalendar  # noqa: F401
        except ImportError:
            self.skipTest("Install notifications extra")
        path = Path(self.tmp.name) / "calendar.ics"
        start = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        event = (
            "BEGIN:VEVENT\nUID:meeting\nDTSTART:"
            + start
            + "\nSUMMARY:Standup\nRRULE:FREQ=DAILY;COUNT=2\nEND:VEVENT\n"
        )
        path.write_text("BEGIN:VCALENDAR\nVERSION:2.0\n" + event + "END:VCALENDAR\n")
        source = Sources(
            self.inbox, self.tmp.name, dict(calendar=str(path), github="", calendar_lead_minutes=10)
        )
        source.calendar()
        self.assertEqual(2, len(self.inbox.items()))
        self.assertIsNone(self.inbox.claim())
        source.calendar()
        self.assertEqual(2, len(self.inbox.items()))
        path.write_text("BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n")
        source.calendar()
        self.assertTrue(all(n["status"] == "cancelled" for n in self.inbox.items()))

    def test_card_preserves_character_above_bottom_third(self):
        args = dict(style="kurisu", emotion="happy", phase=1)
        image = scene.render(
            notification=dict(source="calendar", title="Meeting", body="Soon"), **args
        )
        self.assertEqual((480, 320), image.size)
        self.assertNotEqual(image.getpixel((240, 90)), image.getpixel((0, 90)))
        self.assertNotEqual(image.getpixel((30, 250)), image.getpixel((0, 250)))

    def test_deployment_indicator_animates_without_replacing_character(self):
        args = dict(style="kurisu", emotion="neutral", deploying=True)
        first = scene.render(phase=1, **args)
        second = scene.render(phase=1.3, **args)
        self.assertNotEqual(
            first.crop((10, 10, 60, 25)).tobytes(), second.crop((10, 10, 60, 25)).tobytes()
        )
        self.assertEqual(first.getpixel((240, 90)), second.getpixel((240, 90)))

    def test_dismissed_notification_does_not_announce(self):
        n = self.inbox.publish("system", "Dismiss me")
        self.inbox.dismiss(n["id"])
        self.assertIsNone(self.inbox.claim())

    def test_related_events_share_one_card_and_keep_individual_history(self):
        a = self.inbox.publish(
            "system",
            "Door opened",
            group_key="front-door",
            group_title="Front door activity",
            audio="silent",
            due_at=100,
        )
        b = self.inbox.publish(
            "system",
            "Someone is at the door",
            group_key="front-door",
            group_title="Front door activity",
            audio="silent",
            due_at=102,
        )
        self.assertIsNone(self.inbox.claim(now=102))
        grouped = self.inbox.claim(now=103)
        self.assertEqual(grouped["title"], "Front door activity (2)")
        self.assertEqual(grouped["member_ids"], [a["id"], b["id"]])
        self.assertIn("Door opened", grouped["body"])
        self.assertIn("Someone is at the door", grouped["body"])
        self.inbox.finish(grouped["id"])
        self.assertEqual(
            {i["title"] for i in self.inbox.items()}, {"Door opened", "Someone is at the door"}
        )
        self.assertTrue(all(i["status"] == "delivered" for i in self.inbox.items()))
        self.assertIsNone(self.inbox.claim(now=104))

    def test_group_wait_does_not_hold_unrelated_or_urgent_events(self):
        self.inbox.publish("system", "Door", group_key="front-door", due_at=100)
        other = self.inbox.publish("calendar", "Meeting", due_at=101)
        urgent = self.inbox.publish(
            "system", "Urgent", priority="urgent", group_key="front-door", due_at=101
        )
        self.assertEqual(self.inbox.claim(now=101)["id"], urgent["id"])
        self.assertEqual(self.inbox.claim(now=101)["id"], other["id"])
        self.assertIsNone(self.inbox.claim(now=102))
        self.assertEqual(self.inbox.claim(now=103)["title"], "Door")

    def test_group_boundaries_sources_and_silent_policy(self):
        self.inbox.publish("system", "First", group_key="same", audio="chime", due_at=100)
        self.inbox.publish("system", "Second", group_key="same", audio="silent", due_at=102)
        third = self.inbox.publish("system", "Later", group_key="same", due_at=104)
        other = self.inbox.publish("github", "Separate source", group_key="same", due_at=100)
        group = self.inbox.claim(now=105)
        self.assertEqual(len(group["member_ids"]), 2)
        self.assertEqual(group["audio"], "silent")
        self.inbox.finish(group["id"], "display unavailable")
        self.assertEqual(sum(i["status"] == "failed" for i in self.inbox.items()), 2)
        self.assertEqual(self.inbox.claim(now=105)["id"], other["id"])
        self.assertIsNone(self.inbox.claim(now=106))
        self.assertEqual(self.inbox.claim(now=107)["id"], third["id"])

    def test_dismiss_member_dismisses_whole_claimed_group_and_restart_does_not_replay(self):
        first = self.inbox.publish("system", "First", group_key="group", due_at=100)
        second = self.inbox.publish("system", "Second", group_key="group", due_at=101)
        self.inbox.claim(now=103)
        self.inbox.dismiss(second["id"])
        self.assertTrue(all(i["status"] == "dismissed" for i in self.inbox.items()))
        Inbox(self.tmp.name).recover()
        self.assertIsNone(self.inbox.claim(now=110))
        self.assertNotEqual(first["id"], second["id"])

    def test_existing_queue_schema_migrates_without_losing_notifications(self):
        import json
        import sqlite3

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notifications.sqlite3"
            payload = dict(
                id="old", source="system", title="Saved before upgrade", body="", priority="normal"
            )
            with sqlite3.connect(path) as db:
                db.execute(
                    "CREATE TABLE notifications (id TEXT PRIMARY KEY, dedupe TEXT UNIQUE, payload TEXT, created REAL, due REAL, expires REAL, priority INTEGER, status TEXT, error TEXT)"
                )
                db.execute(
                    "INSERT INTO notifications VALUES (?,?,?,?,?,?,?,?,?)",
                    ("old", "system:old", json.dumps(payload), 100, 100, 500, 1, "pending", None),
                )
            queue = Inbox(folder)
            self.assertEqual(queue.claim(now=101)["title"], "Saved before upgrade")
            queue.finish("old")
            self.assertEqual(queue.items()[0]["status"], "delivered")
            self.assertEqual(Inbox(folder).items()[0]["id"], "old")

    def test_restart_during_group_delivery_does_not_replay_members(self):
        self.inbox.publish("system", "First", group_key="group", due_at=100)
        self.inbox.publish("system", "Second", group_key="group", due_at=101)
        self.inbox.claim(now=103)
        recovered = Inbox(self.tmp.name)
        recovered.recover()
        self.assertTrue(all(i["status"] == "uncertain" for i in recovered.items()))
        self.assertIsNone(recovered.claim(now=104))

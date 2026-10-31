"""Invented calendar/list/transit fixtures; no participant data or provider calls."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from okabebot.amadeus import Store
from okabebot.amadeus_feeds import Feeds, default
from okabebot.amadeus_onboarding import Onboarding, SYSTEM, KEY
from okabebot.adapters.context import FEEDS
from okabebot.morning_digest import Digest, DEFAULTS
from okabebot.morning_briefing import Briefing
from tests.test_amadeus_http import SETUP


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.now = datetime(2032, 5, 3, 8, tzinfo=timezone.utc).timestamp()
        self.owner = Onboarding(self.folder)
        self.addCleanup(self.owner.close)
        self.owner.store.clock = lambda: self.now
        self.owner.save(dict(SETUP, timezone="UTC", sources=[]))
        self.owner.control({"paused": False})
        self.items = {
            "tasks": [
                {
                    "id": "today",
                    "title": "Return imaginary book",
                    "state": "needs_action",
                    "due": "2032-05-03",
                },
                {"id": "future", "title": "Later", "state": "needs_action", "due": "2032-06-03"},
                {"id": "done", "title": "Already done", "state": "completed", "due": "2032-05-02"},
            ],
            "transit": [
                {
                    "id": "rail",
                    "title": "Imaginary line maintenance",
                    "effect": "REDUCED_SERVICE",
                    "routes": "1",
                }
            ],
            "meals": [
                {
                    "id": "dinner",
                    "title": "Imaginary soup",
                    "category": "meal_plan",
                    "start": "2032-05-03T18:00:00Z",
                    "end": "2032-05-03T19:00:00Z",
                },
                {
                    "id": "shopping",
                    "title": "Not a plan",
                    "category": "shopping",
                    "state": "needs_action",
                },
            ],
        }
        self.feeds = Feeds(
            self.folder, clock=lambda: self.now, reader=lambda feed, *a: (self.items[feed.id], True)
        )
        for name, fields in {
            "tasks": {"entities": ["todo.invented"]},
            "transit": {},
            "meals": {"calendars": ["calendar.invented"]},
        }.items():
            self.feeds.configure(
                {"id": name, "config": dict(default(FEEDS[name]), enabled=True, **fields)}
            )
        self.feeds.tick()

    def cards(self):
        with closing(Store(self.folder, clock=lambda: self.now)) as s:
            return Digest(s).cards()

    def test_grounded_relevant_sections_and_no_inferred_empty_day(self):
        cards = self.cards()
        self.assertEqual([c["kind"] for c in cards], ["transit", "tasks", "meals"])
        self.assertNotIn("Later", str(cards))
        self.assertNotIn("Already done", str(cards))
        self.assertNotIn("Not a plan", str(cards))
        self.assertEqual(
            cards[0]["spoken"], "On your selected rail lines: Imaginary line maintenance"
        )

    def test_full_records_find_due_task_outside_compatibility_preview(self):
        self.items["tasks"] = [
            {
                "id": str(i),
                "title": "Future item " + str(i),
                "state": "needs_action",
                "due": "2033-01-01",
            }
            for i in range(25)
        ] + self.items["tasks"][:1]
        self.now += 301
        self.feeds.tick()
        self.assertTrue(any(c["body"] == "Return imaginary book" for c in self.cards()))

    def test_selection_pause_guest_revocation_expiry_and_partial_coverage(self):
        with closing(Store(self.folder, clock=lambda: self.now)) as s:
            Digest(s).configure(dict(DEFAULTS, transit=False, spoken_highlight=False))
            self.assertIsNone(Digest(s).highlight())
        self.assertNotIn("transit", [c["kind"] for c in self.cards()])
        self.owner.control({"paused": True})
        self.assertEqual(self.cards(), [])
        self.owner.control({"paused": False, "guest": True})
        self.assertEqual(self.cards(), [])
        self.owner.control({"guest": False})
        self.now += 901
        self.assertEqual(self.cards(), [])

    def test_highlight_revalidation_and_empty_calendar_omitted_from_speech(self):
        b = Briefing(self.folder, clock=lambda: self.now)
        b.configure(dict(enabled=True, name="Mira", coaching=False, quiet_override=False))
        summary = {
            "cards": [
                {
                    "kind": "calendar",
                    "title": "Today",
                    "body": "No upcoming timed events in this feed",
                }
            ]
            + self.cards()
        }
        spoken, _, _ = b.message(summary, "okabe")
        self.assertIn("Imaginary line maintenance", spoken)
        self.assertNotIn("no more timed events", spoken)
        self.assertEqual(b.revalidate_digest(spoken), spoken)
        with closing(Store(self.folder, clock=lambda: self.now)) as s:
            Digest(s).configure(dict(DEFAULTS, spoken_highlight=False))
        self.assertNotIn("Imaginary line maintenance", b.revalidate_digest(spoken))
        with closing(Store(self.folder, clock=lambda: self.now)) as s:
            Digest(s).configure(dict(DEFAULTS))
        b.message(summary, "okabe")

        with closing(Store(self.folder, clock=lambda: self.now)) as s:
            setup = self.owner.settings()
            s.remember(SYSTEM, KEY, dict(setup, sources=[]))
        self.assertNotIn("Imaginary line maintenance", b.revalidate_digest(spoken))

    def test_controls_are_strict_and_do_not_enable_source_collection(self):
        with closing(Store(self.folder, clock=lambda: self.now)) as s:
            before = self.owner.settings()["sources"]
            with self.assertRaises(ValueError):
                Digest(s).configure(dict(DEFAULTS, tasks="yes"))
            Digest(s).configure(dict(DEFAULTS, meals=False))
            self.assertEqual(self.owner.settings()["sources"], before)

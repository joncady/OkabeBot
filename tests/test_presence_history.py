"""Invented presence histories: reports are not physical-location ground truth."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from okabebot.adapters.context import FEEDS
from okabebot.adapters.context.providers import HomeAssistant
from okabebot.presence_history import timeline
from tests.test_amadeus_feeds import FeedTests


class PresenceTests(unittest.TestCase):
    setUp = FeedTests.setUp
    tearDown = FeedTests.tearDown
    enable = FeedTests.enable

    def load(self, states):
        self.now = datetime(2032, 6, 8, 18, tzinfo=timezone.utc).timestamp()
        midnight = self.now - 18 * 3600
        rows = []
        for index, (hour, state) in enumerate(states):
            rows.append(
                {
                    "id": str(index),
                    "entity_key": "invented-person",
                    "label": "Selected person",
                    "source_type": "person",
                    "state": state,
                    "reported_at": midnight + hour * 3600,
                    "observation": "snapshot" if index == 0 else "change",
                }
            )
        self.feeds.reader = lambda *args: (rows, True)
        self.enable("presence_history", persons=["person.synthetic"])
        self.feeds.tick()
        return timeline(self.path, clock=lambda: self.now)

    def test_away_unknown_and_return_do_not_merge_into_one_interval(self):
        result = self.load(
            [(-1, "home"), (8, "away"), (8.1, "unknown"), (8.2, "away"), (9, "home")]
        )
        self.assertTrue(result["available"])
        self.assertEqual(
            ["unknown", "home"], [i["ended_by"] for i in result["reported_away_intervals"]]
        )
        self.assertEqual("home", result["initial_states"][0]["state"])
        self.assertEqual(4, len(result["transitions"]))
        self.owner.control({"paused": True})
        self.assertFalse(timeline(self.path, clock=lambda: self.now)["available"])

    def test_snapshot_away_never_invents_departure(self):
        result = self.load([(8, "away"), (9, "away"), (10, "home")])
        self.assertEqual([], result["reported_away_intervals"])
        self.assertEqual("snapshot", result["transitions"][0]["observation"])
        self.assertEqual(2, len(result["transitions"]))

    def test_provider_selects_sources_minimizes_and_stabilizes_reports(self):
        now = datetime(2032, 6, 8, 18, tzinfo=timezone.utc).timestamp()
        rows = [
            [
                {
                    "entity_id": "person.synthetic",
                    "state": "home",
                    "last_changed": "2032-06-07T00:00:00Z",
                    "attributes": {"latitude": 99},
                },
                {"state": "not_home", "last_updated": "2032-06-08T08:00:00Z"},
                {"state": "unavailable", "last_updated": "2032-06-08T08:01:00Z"},
            ],
            [{"entity_id": "person.unselected", "state": "home"}],
            [
                {"entity_id": "zone.home", "state": "0", "last_changed": "2032-06-07T00:00:00Z"},
                {"state": "1", "last_updated": "2032-06-08T09:00:00Z"},
            ],
        ]
        provider = HomeAssistant(connection={"url": "http://example.test", "token": "invented"})
        with patch.object(provider, "call", return_value=rows) as call:
            cfg = {"persons": ["person.synthetic"], "zones": ["zone.home"]}
            first, complete = provider.read_feed(FEEDS["presence_history"], cfg, now)
            later, _ = provider.read_feed(FEEDS["presence_history"], cfg, now + 60)
        self.assertEqual(first, later)
        self.assertTrue(complete)
        self.assertEqual(["home", "away", "unknown", "0", "1"], [r["state"] for r in first])
        self.assertNotIn("latitude", str(first))
        self.assertIn("person.synthetic%2Czone.home", call.call_args.args[0])
        self.assertNotIn("unselected", call.call_args.args[0])

    def test_zone_count_does_not_become_person_departure(self):
        self.now = datetime(2032, 6, 8, 18, tzinfo=timezone.utc).timestamp()
        rows = [
            {
                "id": str(i),
                "entity_key": "zone",
                "label": "Home",
                "source_type": "zone",
                "state": str(1 - i),
                "reported_at": self.now - 100 + i,
                "observation": "snapshot" if not i else "change",
            }
            for i in range(2)
        ]
        self.feeds.reader = lambda *args: (rows, True)
        self.enable("presence_history", zones=["zone.home"])
        self.feeds.tick()
        result = timeline(self.path, clock=lambda: self.now)
        self.assertEqual([], result["reported_away_intervals"])
        self.assertEqual("0", result["transitions"][-1]["state"])

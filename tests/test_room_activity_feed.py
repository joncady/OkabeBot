"""Synthetic room activity only; never controls lights or speakers."""

import unittest
from okabebot.adapters.context.providers import HomeAssistant
from okabebot.amadeus_feeds import room_media_busy
from tests import test_amadeus_feeds as fixtures


class RoomActivityTests(unittest.TestCase):
    setUp = fixtures.FeedTests.setUp
    tearDown = fixtures.FeedTests.tearDown
    enable = fixtures.FeedTests.enable
    current = fixtures.FeedTests.current

    def test_minimization_media_gate_freshness_pause_and_no_actuation(self):
        calls = []
        state = {"value": "playing"}

        def read(url, headers, data):
            calls.append((url, data))
            return {
                "state": state["value"] if "media_player." in url else "on",
                "attributes": {
                    "friendly_name": "Imaginary room",
                    "media_title": "Do not retain",
                    "volume_level": 0.4,
                    "brightness": 120,
                },
            }

        provider = HomeAssistant(
            read=read, connection={"url": "http://example.test", "token": "invented"}
        )
        self.feeds.reader = lambda feed, cfg, now: provider.read_feed(feed, cfg, now)
        self.enable(
            "room_activity",
            players=["media_player.imaginary"],
            switches=["switch.imaginary"],
            lights=["light.imaginary"],
        )
        self.assertTrue(room_media_busy(self.owner.store))  # No fresh sample.
        self.feeds.tick()
        self.assertTrue(room_media_busy(self.owner.store))
        items = self.current()[0]["items"]
        self.assertEqual(3, len(items))
        self.assertTrue(all(set(i) == {"id", "label", "state", "category"} for i in items))
        self.assertTrue(all("/api/states/" in url and data is None for url, data in calls))
        for value in ("idle", "paused", "unknown", "unavailable", "buffering"):
            self.now += 61
            state["value"] = value
            self.feeds.tick()
            self.assertEqual(value not in ("idle", "paused"), room_media_busy(self.owner.store))
        state["value"] = "idle"
        self.now += 61
        self.feeds.tick()
        self.assertFalse(room_media_busy(self.owner.store))
        self.now += 151
        self.assertTrue(room_media_busy(self.owner.store))
        self.owner.control({"paused": True})
        self.assertFalse(room_media_busy(self.owner.store))
        self.assertEqual([], self.current())

    def test_switch_only_does_not_gate_speech_or_infer_presence(self):
        self.enable("room_activity", switches=["switch.imaginary"])
        self.assertFalse(room_media_busy(self.owner.store))
        self.assertEqual(
            0,
            self.owner.store.db.execute(
                "SELECT COUNT(*) FROM events WHERE kind IN ('presence','door')"
            ).fetchone()[0],
        )

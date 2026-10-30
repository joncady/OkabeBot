"""Invented home-device metadata; no provider account or physical actions."""

import unittest
from okabebot.adapters.context import FEEDS, validate_config, validate_snapshot
from okabebot.adapters.context.providers import HomeAssistant
from okabebot.amadeus_feeds import default
from tests import test_amadeus_feeds as fixtures


class HomeDeviceTests(unittest.TestCase):
    setUp = fixtures.FeedTests.setUp
    tearDown = fixtures.FeedTests.tearDown
    enable = fixtures.FeedTests.enable
    current = fixtures.FeedTests.current

    def test_home_devices_read_only_minimized_and_recap(self):
        calls = []

        def read(url, headers, data):
            calls.append((url, data))
            return {
                "state": "closed" if "cover." in url else "heat",
                "attributes": {
                    "friendly_name": "Invented device",
                    "current_temperature": 20,
                    "temperature": 21,
                    "hvac_action": "idle",
                    "private_attribute": "never retained",
                },
            }

        provider = HomeAssistant(
            read=read, connection={"url": "http://example.test", "token": "invented"}
        )
        self.feeds.reader = lambda feed, cfg, now: provider.read_feed(feed, cfg, now)
        self.enable("home_devices", covers=["cover.invented"], climates=["climate.invented"])
        self.feeds.tick()
        items = self.current()[0]["items"]
        self.assertEqual(2, len(items))
        self.assertEqual("closed", items[0]["state"])
        self.assertEqual("20", items[1]["current_temperature"])
        self.assertNotIn("private_attribute", str(items))
        from okabebot.tool_reply import facts

        projected = facts("get_context_feed", {"items": [{"value": items[1]}]}, "")
        self.assertEqual("20", projected["records"][0]["current_temperature"])
        self.assertTrue(all("/api/states/" in url and data is None for url, data in calls))
        from okabebot.home_activity import recap

        result = recap(self.path, clock=lambda: self.now + 1)
        self.assertTrue(any(x["kind"] == "home_device" for x in result["observations"]))
        self.owner.control({"paused": True})
        self.assertEqual([], self.current())
        self.assertEqual([], recap(self.path, clock=lambda: self.now + 1)["observations"])

    def test_home_device_configuration_domains_and_snapshot(self):
        feed = FEEDS["home_devices"]
        cfg = default(feed)
        cfg.update(enabled=True, covers=["cover.invented"])
        self.assertEqual(cfg, validate_config(feed, cfg))
        with self.assertRaises(ValueError):
            validate_config(feed, {**cfg, "covers": ["button.invented"]})
        validate_snapshot(
            {
                "provider": "home_devices",
                "complete": "yes",
                "valid_until_at": self.now + 900,
                "items": [
                    {"id": "invented", "label": "Door", "state": "unavailable", "category": "cover"}
                ],
            }
        )

"""Invented provider fixtures only; no account, household or trial records."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from okabebot.amadeus import Store
from okabebot.amadeus_feeds import Feeds, context, default
from okabebot.amadeus_onboarding import Onboarding
from okabebot.adapters.context import FEEDS, validate_config, validate_snapshot
from okabebot.adapters.context.providers import HomeAssistant, transit, trakt
from tests.test_amadeus_http import SETUP


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.now = 2_000_000_000
        self.owner = Onboarding(self.path)
        self.owner.store.clock = lambda: self.now
        self.owner.save(dict(SETUP, sources=[]))
        self.owner.control({"paused": False})
        self.calls = []
        self.items = [
            {"id": "invented-task", "title": "Water imaginary fern", "state": "needs_action"}
        ]

        def reader(feed, cfg, now):
            self.calls.append(feed.id)
            if feed.id != "tasks":
                raise RuntimeError("secret-provider-url-must-not-leak")
            return self.items, True

        self.feeds = Feeds(self.path, clock=lambda: self.now, reader=reader)

    def tearDown(self):
        self.owner.close()
        self.tmp.cleanup()

    def enable(self, name="tasks", **values):
        cfg = default(FEEDS[name])
        cfg.update(enabled=True, **values)
        return self.feeds.configure({"id": name, "config": cfg})

    def current(self):
        with closing(Store(self.path, clock=lambda: self.now)) as store:
            return context(store)

    def test_consent_before_io_private_context_and_empty_snapshot_clears(self):
        self.feeds.tick()
        self.assertEqual(self.calls, [])
        self.enable(entities=["todo.invented"])
        self.feeds.tick()
        self.assertEqual(self.current()[0]["items"], self.items)
        self.assertEqual(self.calls, ["tasks"])
        self.feeds.tick()
        self.assertEqual(len(self.calls), 1)
        self.now += 301
        self.items = []
        self.feeds.tick()
        self.assertEqual(self.current()[0]["items"], [])
        self.now += 901
        self.assertEqual(self.current(), [])

    def test_pause_guest_revocation_and_forget_during_network_discard(self):
        self.enable(entities=["todo.invented"])
        self.owner.control({"guest": True})
        self.feeds.tick()
        self.assertEqual(self.calls, [])
        self.owner.control({"guest": False})

        def forget(*args):
            self.owner.forget({"confirm": "forget_amadeus"})
            return self.items, True

        self.feeds.reader = forget
        self.feeds.tick()
        self.assertEqual(self.current(), [])
        self.assertEqual(
            self.owner.store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0
        )

    def test_failure_isolation_truncation_and_config_change_in_flight(self):
        self.enable(entities=["todo.invented"])
        self.enable("appliances", entities=["sensor.invented_cycle"])
        self.items *= 25
        self.feeds.tick()
        self.assertFalse(self.current()[0]["complete"])
        states = {f["id"]: f["status"] for f in self.feeds.snapshot()["feeds"]}
        self.assertEqual(states["appliances"], "unavailable_check_setup")
        self.assertNotIn("secret-provider", json.dumps(states))
        self.now += 301

        def rebind(*args):
            self.enable(entities=["todo.other"])
            return self.items[:1], True

        self.feeds.reader = rebind
        self.feeds.tick()
        self.assertEqual(self.current(), [])

    def test_credentials_are_write_only_and_not_exported(self):
        result = self.feeds.connect(
            {"transport": "ha", "url": "http://example.test:8123", "token": "invented-secret"}
        )
        self.assertNotIn("invented-secret", json.dumps(result))
        self.assertNotIn("invented-secret", json.dumps(self.owner.export()))
        self.assertTrue(result["connections"][0]["has_token"])
        with self.assertRaises(ValueError):
            self.feeds.connect(
                {"transport": "ha", "url": "http://user:pass@example.test", "token": "x"}
            )

    def test_disconnect_disables_shared_feeds_and_clears_current_context(self):
        self.feeds.connect({"transport": "ha", "url": "http://example.test", "token": "invented"})
        self.enable(entities=["todo.invented"])
        self.feeds.tick()
        self.assertTrue(self.current())
        self.feeds.connect({"transport": "ha", "disconnect": True})
        self.assertEqual(self.current(), [])
        self.assertFalse(
            next(f for f in self.feeds.snapshot()["feeds"] if f["id"] == "tasks")["config"][
                "enabled"
            ]
        )

    def test_strict_schemas_reject_unexpected_data_and_wrong_entities(self):
        with self.assertRaises(ValueError):
            validate_config(FEEDS["tasks"], {"enabled": True, "entities": ["switch.light"]})
        with self.assertRaises(ValueError):
            validate_config(FEEDS["transit"], {"enabled": True, "routes": ["traffic"]})
        with self.assertRaises(ValueError):
            validate_snapshot(
                {
                    "provider": "tasks",
                    "complete": "yes",
                    "valid_until_at": self.now,
                    "items": [{"id": "x", "raw_description": "not permitted"}],
                }
            )

    def test_ha_realistic_task_activity_appliance_and_meal_shapes(self):
        def read(url, headers, data):
            if "/services/todo/" in url:
                return {
                    "service_response": {
                        data["entity_id"]: {
                            "items": [
                                {
                                    "uid": "synthetic-uid",
                                    "summary": "Invented oats",
                                    "status": "needs_action",
                                    "description": "must not be collected",
                                    "due": "2033-05-20",
                                }
                            ]
                        }
                    }
                }
            if "/calendars/" in url:
                return [
                    {
                        "summary": "Invented soup",
                        "start": {"date": "2033-05-20"},
                        "end": {"date": "2033-05-21"},
                        "description": "not collected",
                    }
                ]
            return {
                "state": "on",
                "attributes": {"friendly_name": "Invented washer", "gps": "not collected"},
            }

        ha = HomeAssistant(read=read, connection={"url": "http://example.test", "token": "fake"})
        for name, cfg in [
            ("tasks", {"entities": ["todo.synthetic"]}),
            ("meals", {"shopping": ["todo.synthetic"], "calendars": ["calendar.synthetic"]}),
            ("appliances", {"entities": ["sensor.synthetic"]}),
            (
                "device_activity",
                {"charging": ["binary_sensor.synthetic"], "focus": [], "locked": []},
            ),
        ]:
            items, complete = ha.read_feed(FEEDS[name], cfg, self.now)
            validate_snapshot(
                dict(provider=name, items=items, complete="yes", valid_until_at=self.now + 60)
            )
            self.assertTrue(complete)
            self.assertNotIn("not collected", json.dumps(items))
            self.assertNotIn("must not", json.dumps(items))

    def test_sound_transit_active_periods_route_filter_and_freshness(self):
        def alert(id, routes, start, end):
            return {
                "id": id,
                "alert": {
                    "header_text": {"translation": [{"language": "en", "text": "Invented delay"}]},
                    "effect": "SIGNIFICANT_DELAYS",
                    "active_period": [{"start": start, "end": end}],
                    "informed_entity": [{"route_id": r} for r in routes],
                },
            }

        value = {
            "header": {"timestamp": str(self.now)},
            "entity": [
                alert("one", ["100479"], self.now - 60, self.now + 60),
                alert("two", ["2LINE"], self.now - 60, self.now + 60),
                alert("sounder", ["SNDR_TL"], self.now - 60, self.now + 60),
                alert("future", ["100479"], self.now + 60, self.now + 120),
                alert("expired", ["100479"], self.now - 120, self.now - 60),
            ],
        }
        items, complete = transit(value, {"routes": ["1", "2"]}, self.now)
        self.assertEqual(len(items), 2)
        self.assertEqual({i["routes"] for i in items}, {"1 Line", "2 Line"})
        self.assertTrue(complete)
        with self.assertRaises(ValueError):
            transit(value, {"routes": []}, self.now + 901)

    def test_trakt_confirmed_recent_watches_not_ratings_or_availability(self):
        value = [
            {
                "id": 1,
                "type": "movie",
                "watched_at": datetime.fromtimestamp(self.now - 60, timezone.utc).isoformat(),
                "movie": {"title": "Invented Moon", "ids": {"trakt": 123}},
            }
        ]
        items, complete = trakt(value, self.now)
        self.assertFalse(complete)
        self.assertEqual(items[0]["title"], "Invented Moon")
        self.assertNotIn("liked", json.dumps(items))
        validate_snapshot(
            dict(provider="watch_history", items=items, complete="no", valid_until_at=self.now + 60)
        )

    def test_feed_context_reaches_conversation_without_network_or_memory_write(self):
        from okabebot.amadeus_text import TextConversation

        self.enable(entities=["todo.invented"])
        self.feeds.tick()
        profile = self.owner.subject()
        self.owner.store.remember(profile, "conversation.preferences", {"enabled": True})
        chat = TextConversation(self.path, clock=lambda: self.now)
        seen = []

        def generate(text, data):
            seen.extend(data["source_context"])
            return {"reply": "The invented fern task is on your connected list.", "memory": None}

        chat.send("What is on my task list?", generate)
        self.assertEqual(seen[0]["source"], "tasks")


if __name__ == "__main__":
    unittest.main()

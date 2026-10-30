"""Invented context-policy regressions; no household data or actuators."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from okabebot.amadeus import Store
from okabebot.amadeus_habits import configure
from okabebot.amadeus_onboarding import KEY, SYSTEM
from okabebot.amadeus_opportunities import ContextPlanner, configure_context


class OpportunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = datetime(2030, 1, 7, 18, tzinfo=timezone.utc).timestamp()
        self.sources = ["phone_context", "door_presence", "media", "calendar", "availability"]
        self.store = Store(Path(self.tmp.name), sources=self.sources, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.store.remember(
            SYSTEM,
            KEY,
            dict(
                profile="fiction",
                sources=self.sources,
                timezone="UTC",
                paused=False,
                guest=False,
                quiet_start="22:00",
                quiet_end="07:00",
            ),
        )
        configure(self.store, enabled=True)
        self.prefs = {
            "goals": [{"kind": "media", "enabled": True}],
            "media": {
                "genres": ["mystery"],
                "allow_discovery": True,
                "avoid": ["graphic violence"],
                "providers": ["Fictional"],
                "watched_titles": ["Seen"],
                "max_minutes": 90,
            },
        }
        self.catalog = [
            dict(
                id=str(n),
                title=t,
                genres=["mystery"],
                content_tags=tags,
                minutes=minutes,
                provider="Fictional",
            )
            for n, (t, tags, minutes) in enumerate(
                [
                    ("New", [], 30),
                    ("Seen", [], 30),
                    ("Too long", [], 150),
                    ("Unsafe", ["graphic violence"], 30),
                ]
            )
        ]
        self.planner = ContextPlanner(self.store)
        self.counter = 0

    def event(self, source, kind, payload, age=0):
        self.counter += 1
        self.store.observe(
            source=source,
            external_id=str(self.counter),
            kind=kind,
            subject="fiction",
            observed_at=self.now - age,
            payload=payload,
        )

    def ready(self):
        configure_context(self.store, "fiction", self.prefs, self.catalog)
        self.event("door_presence", "presence", {"state": "home"})
        self.event("phone_context", "phone_wake", {"state": "on"})
        for signal in ["dnd", "focus"]:
            self.event(
                "availability",
                "availability",
                {"signal": signal, "state": "off", "observation": "snapshot"},
            )
        self.event(
            "calendar",
            "calendar_snapshot",
            {
                "snapshot_id": "s",
                "start_at": self.now,
                "end_at": self.now + 86400,
                "event_count": 0,
                "busy_coverage": "complete",
            },
        )

    def test_default_off_and_actual_matching_catalogue(self):
        self.assertEqual(self.planner.snapshot()["state"], "disabled")
        self.ready()
        p = self.planner.snapshot()["proposals"][0]
        self.assertTrue(p["eligible"])
        self.assertEqual([c["title"] for c in p["context"]["choices"]], ["New"])
        self.planner.acknowledge(p)
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_new_context_sources_create_shadow_candidates_and_exclude_watched_movie(self):
        self.ready()
        from okabebot.amadeus_habits import preference

        extra = ["tasks", "transit", "appliances", "watch_history"]
        setup = preference(self.store, SYSTEM, KEY)
        setup["sources"] += extra
        self.store.remember(SYSTEM, KEY, setup)
        self.store.sources = frozenset(set(self.sources) | set(extra))
        fixtures = {
            "tasks": [
                {
                    "id": "task",
                    "title": "Invented errand",
                    "state": "needs_action",
                    "due": datetime.fromtimestamp(self.now + 3600, timezone.utc).isoformat(),
                }
            ],
            "transit": [
                {
                    "id": "alert",
                    "title": "Invented delay",
                    "effect": "SIGNIFICANT_DELAYS",
                    "routes": "1 Line",
                }
            ],
            "appliances": [{"id": "washer", "label": "Invented washer", "state": "finished"}],
            "watch_history": [
                {"id": "watch", "title": "New", "type": "movie", "watched_at": self.now - 60}
            ],
        }
        for source, items in fixtures.items():
            self.store.remember(SYSTEM, "feed." + source, {"enabled": True})
            self.event(
                source,
                "feed_snapshot",
                {
                    "provider": source,
                    "items": items,
                    "complete": "yes",
                    "valid_until_at": self.now + 600,
                },
            )
        proposals = self.planner.snapshot()["proposals"]
        self.assertEqual({p["kind"] for p in proposals}, {"tasks", "transit", "appliances"})
        self.assertTrue(all(p["shadow"] for p in proposals))
        self.event("media", "media", {"app": "Invented Player", "state": "PLAYING"})
        self.assertTrue(all(not p["eligible"] for p in self.planner.snapshot()["proposals"]))

    def test_any_player_active_even_if_another_stopped(self):
        self.ready()
        self.event("media", "media", {"app": "Music", "state": "PLAYING"}, age=2)
        self.event("media", "media", {"app": "Video", "state": "IDLE"})
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_focus_and_unknown_fail_closed(self):
        self.ready()
        self.event(
            "availability",
            "availability",
            {"signal": "focus", "state": "on", "observation": "change"},
        )
        self.assertEqual(
            self.planner.snapshot()["proposals"][0]["reason"], "focus_active_or_unknown"
        )

    def test_ongoing_busy_event_blocks_after_start_window(self):
        self.ready()
        self.event(
            "calendar",
            "calendar",
            {
                "snapshot_id": "s",
                "summary": "Fictional appointment",
                "start_at": self.now - 7200,
                "end_at": self.now + 3600,
                "busy": "busy",
            },
        )
        self.assertEqual(self.planner.snapshot()["proposals"][0]["reason"], "calendar_busy")

    def test_revalidate_acknowledgment(self):
        self.ready()
        p = self.planner.snapshot()["proposals"][0]
        self.event(
            "availability",
            "availability",
            {"signal": "dnd", "state": "on", "observation": "change"},
        )
        with self.assertRaises(ValueError):
            self.planner.acknowledge(p)

    def test_tv_attention_and_unknown_are_not_idle(self):
        self.sources.append("tv_usage")
        self.store.sources = frozenset(self.sources)
        setup = dict(
            self.store.db.execute(
                "SELECT * FROM preferences WHERE subject=? AND key=?", (SYSTEM, KEY)
            ).fetchone()
        )
        import json

        value = json.loads(setup["value"])
        value["sources"] = self.sources
        self.store.remember(SYSTEM, KEY, value)
        self.ready()
        self.event(
            "tv_usage",
            "tv_state",
            {"state": "playing", "device_id": "fictional-tv", "observation": "change"},
        )
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_failed_configuration_keeps_previous_catalogue(self):
        self.ready()
        with self.assertRaises(ValueError):
            configure_context(
                self.store, "fiction", self.prefs, [dict(self.catalog[0], provider=4)]
            )
        self.assertEqual(
            self.planner.snapshot()["proposals"][0]["context"]["choices"][0]["title"], "New"
        )

    def test_midnight_check_does_not_create_morning(self):
        self.now = datetime(2030, 1, 7, 12, tzinfo=timezone.utc).timestamp()
        self.prefs["goals"] = [{"kind": "morning", "enabled": True}]
        self.ready()
        self.event(
            "phone_context",
            "weather",
            {"condition": "rainy", "temperature_c": 10, "reported_at": self.now},
        )
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_snapshot_room_on_is_not_an_arrival(self):
        self.ready()
        self.event("phone_context", "phone_wake", {"state": "off"})
        self.event(
            "availability",
            "availability",
            {"signal": "room", "state": "on", "observation": "snapshot"},
        )
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_exposure_is_not_watched_and_blocks_repeated_choices(self):
        from okabebot.amadeus_habits import preference

        self.ready()
        p = self.planner.snapshot()["proposals"][0]
        # Caller-supplied choices must not be used to write exposure evidence.
        forged = dict(p, context={"choices": [dict(self.catalog[0], id="forged")]})
        self.planner.acknowledge(forged)
        saved = preference(self.store, "fiction", "context.preferences")
        self.assertEqual(saved["media"]["watched_titles"], ["Seen"])
        exposures = self.store.db.execute("SELECT identity FROM context_exposures").fetchall()
        self.assertEqual(len(exposures), 1)
        self.assertNotIn("forged", exposures[0][0])
        self.now += 86400
        self.ready()
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_preview_and_invalid_ack_do_not_record_exposure(self):
        self.ready()
        p = self.planner.snapshot()["proposals"][0]
        self.planner.snapshot()
        with self.assertRaises(ValueError):
            self.planner.acknowledge(dict(p, proposal_id="forged"))
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM context_exposures").fetchone()[0],
            0,
        )

    def test_profile_forget_removes_exposure_and_config(self):
        self.ready()
        self.planner.acknowledge(self.planner.snapshot()["proposals"][0])
        self.store.forget("fiction")
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM context_exposures").fetchone()[0], 0
        )
        self.assertEqual(self.planner.snapshot()["state"], "disabled")

    def test_prune_clears_expired_exposure(self):
        self.ready()
        self.planner.acknowledge(self.planner.snapshot()["proposals"][0])
        self.now += 8 * 86400
        self.store.prune()
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM context_exposures").fetchone()[0], 0
        )

    def test_evening_screen_inactivity_is_not_sleep(self):
        self.now = datetime(2030, 1, 7, 21, tzinfo=timezone.utc).timestamp()
        self.prefs["goals"] = [{"kind": "morning", "enabled": True}]
        self.ready()
        self.event("phone_context", "phone_wake", {"state": "off"}, age=4 * 3600)
        self.event("phone_context", "phone_wake", {"state": "on"})
        self.event(
            "phone_context",
            "weather",
            {"condition": "sunny", "temperature_c": 20, "reported_at": self.now},
        )
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_sustained_dnd_release_prepares_overview(self):
        self.now = datetime(2030, 1, 7, 12, tzinfo=timezone.utc).timestamp()
        self.prefs["goals"] = [{"kind": "morning", "enabled": True}]
        self.ready()
        self.store.db.execute(
            "DELETE FROM events WHERE kind='availability' AND json_extract(payload,'$.signal')='dnd'"
        )
        self.event(
            "availability",
            "availability",
            {"signal": "dnd", "state": "on", "observation": "snapshot"},
            age=5 * 3600,
        )
        self.event(
            "availability",
            "availability",
            {"signal": "dnd", "state": "off", "observation": "change"},
        )
        self.event(
            "phone_context",
            "weather",
            {"condition": "rainy", "temperature_c": 10, "reported_at": self.now},
        )
        self.assertTrue(self.planner.snapshot()["proposals"][0]["eligible"])

    def test_stale_playing_does_not_become_available(self):
        self.ready()
        self.event("media", "media", {"app": "Music", "state": "PLAYING"}, age=86400)
        self.assertEqual(self.planner.snapshot()["proposals"][0]["reason"], "media_attention")

    def test_multiple_dnd_devices_must_all_be_off(self):
        self.ready()
        self.event(
            "availability",
            "availability",
            {"signal": "dnd", "device_id": "tablet", "state": "on", "observation": "change"},
            age=2,
        )
        self.event(
            "availability",
            "availability",
            {"signal": "dnd", "device_id": "phone", "state": "off", "observation": "snapshot"},
        )
        self.assertEqual(self.planner.snapshot()["proposals"][0]["reason"], "dnd_active_or_unknown")

    def test_alarm_plus_room_opening_does_not_require_screen(self):
        self.now = datetime(2030, 1, 7, 12, tzinfo=timezone.utc).timestamp()
        self.prefs["goals"] = [{"kind": "morning", "enabled": True}]
        self.ready()
        self.event("phone_context", "phone_wake", {"state": "off"})
        self.event("phone_context", "phone_alarm", {"alarm_at": self.now})
        self.event(
            "phone_context",
            "weather",
            {"condition": "sunny", "temperature_c": 20, "reported_at": self.now},
        )
        self.event(
            "availability",
            "availability",
            {"signal": "room", "state": "on", "observation": "change"},
        )
        self.assertTrue(self.planner.snapshot()["proposals"][0]["eligible"])

    def test_cold_start_requires_explicit_discovery(self):
        self.prefs["media"].pop("allow_discovery")
        self.ready()
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_prior_playback_today_prevents_late_choice_prompt(self):
        self.ready()
        self.event("media", "media", {"app": "Player", "state": "PLAYING"}, age=7200)
        self.event("media", "media", {"app": "Player", "state": "IDLE"})
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_full_day_agenda_does_not_expand_media_budget_context(self):
        self.ready()
        self.event(
            "calendar",
            "calendar",
            {
                "snapshot_id": "s",
                "summary": "Late invented appointment",
                "start_at": self.now + 5 * 3600,
                "end_at": self.now + 6 * 3600,
                "busy": "busy",
            },
        )
        context = self.planner.snapshot()["proposals"][0]["context"]
        self.assertEqual(context["upcoming"], [])
        self.assertEqual(context["day_agenda"][0]["summary"], "Late invented appointment")
        context["weather"] = {"temperature_c": 14, "condition": "partlycloudy"}
        from zoneinfo import ZoneInfo

        brief = self.planner._brief(context, ZoneInfo("UTC"), whole_day=True)
        self.assertIn("partly cloudy", brief)
        self.assertIn("Late invented appointment", brief)

    def test_stale_terminal_player_state_retires_session(self):
        self.ready()
        self.event("media", "media", {"app": "Old player", "state": "IDLE"}, age=86400)
        self.assertTrue(self.planner.snapshot()["proposals"][0]["eligible"])

    def test_room_off_change_followed_by_on_snapshot_is_not_opening(self):
        self.ready()
        self.event("phone_context", "phone_wake", {"state": "off"})
        self.event(
            "availability",
            "availability",
            {"signal": "room", "device_id": "living", "state": "off", "observation": "change"},
            age=10,
        )
        self.event(
            "availability",
            "availability",
            {"signal": "room", "device_id": "living", "state": "on", "observation": "snapshot"},
        )
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_different_room_change_does_not_open_current_room(self):
        self.ready()
        self.event("phone_context", "phone_wake", {"state": "off"})
        self.event(
            "availability",
            "availability",
            {"signal": "room", "device_id": "kitchen", "state": "on", "observation": "change"},
            age=10,
        )
        self.event(
            "availability",
            "availability",
            {"signal": "room", "device_id": "living", "state": "on", "observation": "snapshot"},
        )
        self.assertEqual(self.planner.snapshot()["proposals"], [])

    def test_dnd_policy_off_still_requires_focus_and_other_attention(self):
        self.ready()
        self.event(
            "availability",
            "availability",
            {"signal": "dnd", "state": "on", "observation": "change"},
        )
        # Bind the private profile from this synthetic fixture rather than assuming its name.
        from okabebot.amadeus_habits import preference

        profile = preference(self.store, SYSTEM, KEY)["profile"]
        self.store.remember(profile, "conversation.interruptions", {"respect_dnd": False})
        self.assertIsNone(
            self.planner._attention_gate(
                [
                    dict(r, payload=json.loads(r["payload"]))
                    for r in self.store.db.execute(
                        "SELECT * FROM events ORDER BY observed_at,rowid"
                    )
                ],
                preference(self.store, SYSTEM, KEY),
                self.now,
            )
        )

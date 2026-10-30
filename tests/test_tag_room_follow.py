"""Synthetic NFC scan→room→movement pipeline; no real hardware or person identity."""

import unittest
from okabebot.amadeus_onboarding import SYSTEM
from okabebot.tag_rooms import TagRoomFollow
from tests import test_tag_areas as fixtures


class RoomFollowTests(unittest.TestCase):
    inventory = fixtures.TagAreaTests.inventory

    def setUp(self):
        fixtures.TagAreaTests.setUp(self)
        self.places = [
            {
                "id": "screen",
                "name": "Imaginary screen",
                "approved": True,
                "adapter": "pi",
                "available": True,
            }
        ]
        self.owner.store.remember(SYSTEM, "home_map.bindings", {"screen": "bath"})
        self.follow = TagRoomFollow(
            self.folder,
            lambda: self.places,
            lambda target: self.calls.append(target) or {"accepted": True},
            clock=lambda: self.now,
        )
        self.tags.room_follow = self.follow
        self.tags.locations = self.follow.locations
        self.areas.refresh()

    def enable(self, **extra):
        self.tags.save(
            {
                "tag_id": "stable-tag",
                "name": "Room tag",
                "action": "room_checkin",
                "enabled": True,
                **extra,
            }
        )

    def scan(self, event="invented-event"):
        return self.tags.scan({"tag_id": "stable-tag", "event_id": event, "observed_at": self.now})

    def test_opt_in_only_and_chore_scan_completes_and_moves_once(self):
        self.assertEqual("chore_completed", self.scan()["status"])
        self.assertEqual([], self.calls)
        self.assertIsNone(self.follow.cue())
        self.now += 4
        self.tags.save(
            {
                "tag_id": "stable-tag",
                "name": "Room chore",
                "action": "chore_reminder",
                "chore_id": self.chore["id"],
                "enabled": True,
                "room_follow": True,
            }
        )
        self.assertEqual("real_scan_required", self.tags.dispatch("stable-tag")["status"])
        result = self.scan("next-event")
        self.assertEqual("chore_completed", result["status"])
        self.assertEqual("room_move_requested", result["room_status"])
        self.assertEqual(["screen"], self.calls)
        self.assertEqual("duplicate", self.scan("next-event")["status"])
        self.assertEqual(["screen"], self.calls)
        cue = self.follow.cue()
        self.assertEqual("bath", cue["area_id"])
        self.assertEqual("unknown", cue["identity"])
        self.assertEqual(
            0,
            self.owner.store.db.execute(
                "SELECT COUNT(*) FROM events WHERE kind IN ('presence','door')"
            ).fetchone()[0],
        )

    def test_registration_and_test_never_claim_a_room_real_scan_expires(self):
        self.enable(room_minutes=1)
        self.assertEqual("real_scan_required", self.tags.dispatch("stable-tag")["status"])
        self.tags.learn()
        self.assertEqual("registered_for_review", self.scan()["status"])
        self.assertIsNone(self.follow.cue())
        self.assertEqual([], self.calls)
        self.now += 91
        self.assertEqual("room_move_requested", self.scan("real-scan")["status"])
        self.assertIsNone(self.chores.snapshot()["items"][0]["last_done_at"])
        self.now += 61
        self.assertIsNone(self.follow.cue())

    def test_ambiguous_room_requires_choice_and_reassignment_never_moves_wrong_room(self):
        self.places.append(
            {
                "id": "tv",
                "name": "Imaginary TV",
                "approved": True,
                "adapter": "cast",
                "available": True,
            }
        )
        self.owner.store.remember(SYSTEM, "home_map.bindings", {"screen": "bath", "tv": "bath"})
        self.enable()
        self.assertEqual("room_screen_ambiguous", self.scan()["status"])
        self.assertEqual([], self.calls)
        self.assertIsNotNone(self.follow.cue())
        self.enable(room_location_id="tv")
        self.now += 4
        self.assertEqual("room_move_requested", self.scan("chosen")["status"])
        self.assertEqual(["tv"], self.calls)
        self.owner.store.remember(SYSTEM, "home_map.bindings", {"screen": "bath", "tv": "hall"})
        self.now += 4
        self.assertEqual("room_move_requested", self.scan("moved")["status"])
        self.assertEqual(["tv", "screen"], self.calls)
        self.enable(room_location_id="tv")

    def test_stale_metadata_pause_rebind_disable_and_uncertain_failure(self):
        self.enable()
        self.follow.call = lambda target: (_ for _ in ()).throw(OSError("invented failure"))
        self.assertEqual("room_move_failed", self.scan()["status"])
        self.assertEqual("duplicate", self.scan()["status"])
        self.assertIsNotNone(self.follow.cue())
        self.now += 1
        self.owner.control({"paused": True})
        self.assertIsNone(self.follow.cue())
        self.now += 1
        self.owner.control({"paused": False})
        self.assertIsNone(self.follow.cue())
        self.now += 601
        self.assertEqual("tag_room_unavailable", self.scan("stale")["status"])
        self.assertIsNone(self.follow.cue())
        self.areas.refresh()
        self.now += 4
        self.scan("fresh")
        self.assertIsNotNone(self.follow.cue())
        self.enable(enabled=False)
        self.assertIsNone(self.follow.cue())

    def test_unavailable_browser_and_changed_context_do_not_move(self):
        self.places[0].update(adapter="browser", available=False)
        self.enable()
        self.assertEqual("room_screen_unavailable", self.scan()["status"])
        self.assertEqual([], self.calls)
        self.assertIsNotNone(self.follow.cue())

    def test_changed_room_resolution_is_rechecked_before_move(self):
        from unittest.mock import patch

        self.enable()
        original = self.follow.plan
        ready = original("stable-tag", {"action": "room_checkin"})
        with patch.object(
            self.follow, "plan", side_effect=[ready, {"status": "tag_room_unavailable"}]
        ):
            self.assertEqual("room_context_changed", self.scan()["status"])
        self.assertEqual([], self.calls)

    def test_room_questions_use_read_tool_and_keep_scanner_identity_unknown(self):
        from okabebot.local_conversation import shortlist, acknowledgement
        from okabebot.tool_reply import facts

        self.enable()
        self.scan()
        self.assertEqual(
            ["get_companion_locations"],
            shortlist("Which room am I in?", {"get_companion_locations": {}}),
        )
        result = {"locations": [], "current_location": None, "room_cue": self.follow.cue()}
        self.assertIn(
            "scanner's identity is unknown", acknowledgement("get_companion_locations", result)
        )
        projected = facts("get_companion_locations", result, "")
        self.assertEqual("unknown", projected["room_cue"]["identity"])

    def test_explicit_cross_area_fallback_only_without_local_screen_and_cue_stays_local(self):
        self.owner.store.remember(SYSTEM, "home_map.bindings", {"screen": "hall"})
        self.enable()
        self.assertEqual("room_screen_unassigned", self.scan()["status"])
        self.assertEqual([], self.calls)
        self.enable(room_location_id="screen")
        self.now += 4
        self.assertEqual("room_move_requested", self.scan("fallback")["status"])
        self.assertEqual(["screen"], self.calls)
        self.assertEqual("bath", self.follow.cue()["area_id"])
        self.assertEqual("Imaginary hall", self.follow.locations()[0]["area_name"])

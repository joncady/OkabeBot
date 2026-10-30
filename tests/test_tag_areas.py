"""Invented registry identities/rooms; no account, real tags or physical actions."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from okabebot.amadeus_onboarding import Onboarding, SYSTEM
from okabebot.chores import Chores, chore_label
from okabebot.ha_inventory import normalize
from okabebot.tag_areas import TagAreas
from okabebot.tags import Tags
from tests.test_amadeus_http import SETUP


class TagAreaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "amadeus"
        self.now = 2_000_000_000
        self.owner = Onboarding(self.folder)
        self.addCleanup(self.owner.close)
        self.owner.save(dict(SETUP, sources=[]))
        self.owner.control({"paused": False})
        self.owner.store.clock = lambda: self.now
        self.owner.store.remember(
            SYSTEM, "feed_connection.ha", {"url": "http://example.test", "token": "invented"}
        )
        self.owner.store.remember(SYSTEM, "feed_connection_revision.ha", "generation-a")
        self.area = "bath"
        self.name = "Imaginary bathroom"
        self.present = True
        self.areas = TagAreas(self.folder, self.inventory, clock=lambda: self.now)
        self.chores = Chores(self.folder, clock=lambda: self.now)
        self.chore = self.chores.save(
            {"title": "Change towels", "interval_days": 14, "repeat_days": 1, "enabled": True}
        )["item"]
        self.calls = []
        self.tags = Tags(
            self.folder.parent / "tags",
            lambda: [{"id": "screen", "name": "Screen", "approved": True}],
            self.calls.append,
            clock=lambda: self.now,
            chores=self.chores,
            areas=self.areas.snapshot,
        )
        self.tags.save(
            {
                "tag_id": "stable-tag",
                "name": "Towels",
                "action": "chore_reminder",
                "chore_id": self.chore["id"],
                "enabled": True,
            }
        )

    def inventory(self):
        return normalize(
            [
                [
                    {"area_id": "bath", "name": self.name},
                    {"area_id": "hall", "name": "Imaginary hall"},
                ],
                [],
                [
                    {
                        "entity_id": "tag.renamed_entity",
                        "platform": "tag",
                        "unique_id": "stable-tag",
                        "area_id": self.area,
                    }
                ]
                if self.present
                else [],
                [],
            ]
        )

    def test_exact_tag_identity_inheritance_rename_move_unassign_remove_no_completion(self):
        self.assertEqual("ready", self.areas.refresh()["state"])
        mapping = self.tags.snapshot()["mappings"][0]
        self.assertEqual("assigned", mapping["area_status"])
        self.assertEqual(self.name, mapping["ha_area"]["room"])
        item = self.chores.snapshot()["items"][0]
        self.assertEqual(self.name, item["rooms"][0]["room"])
        self.assertIsNone(item["last_done_at"])
        self.assertEqual(self.chore["due_at"], item["due_at"])
        self.assertIn("Imaginary bathroom", chore_label(item))
        from okabebot.tool_reply import facts

        facts_value = facts("get_chores", self.chores.context(True), "")
        self.assertEqual(self.name, facts_value["chores"][0]["rooms"][0]["room"])
        self.name = "Renamed bath"
        self.areas.refresh()
        self.assertEqual(self.name, self.chores.context(True)["items"][0]["rooms"][0]["room"])
        self.area = "hall"
        self.areas.refresh()
        self.assertEqual("hall", self.chores.snapshot()["items"][0]["rooms"][0]["area_id"])
        self.area = None
        self.areas.refresh()
        self.assertEqual("unassigned", self.tags.snapshot()["mappings"][0]["area_status"])
        self.assertEqual([], self.chores.snapshot()["items"][0]["rooms"])
        self.present = False
        self.areas.refresh()
        self.assertEqual("missing", self.tags.snapshot()["mappings"][0]["area_status"])
        self.assertEqual([], self.calls)

    def test_expiry_disconnect_rebind_ambiguous_and_pause(self):
        self.areas.refresh()
        self.now += 601
        self.assertEqual([], self.chores.snapshot()["items"][0]["rooms"])
        self.assertEqual("stale", self.tags.snapshot()["mappings"][0]["area_status"])
        self.areas.refresh()
        self.owner.store.remember(SYSTEM, "feed_connection_revision.ha", "generation-b")
        self.assertEqual([], self.chores.snapshot()["items"][0]["rooms"])

        def changed():
            self.owner.store.remember(SYSTEM, "feed_connection_revision.ha", "generation-c")
            return self.inventory()

        self.areas.inventory = changed
        self.assertEqual("context_changed", self.areas.refresh()["state"])
        self.areas.inventory = lambda: {"tags": [self.inventory()["tags"][0]] * 2}
        self.areas.refresh()
        self.assertEqual([], self.chores.snapshot()["items"][0]["rooms"])
        self.owner.store.db.execute(
            "DELETE FROM preferences WHERE subject=? AND key=?", (SYSTEM, "feed_connection.ha")
        )
        self.owner.store.db.commit()
        self.assertEqual("not_connected", self.areas.snapshot()["state"])
        self.owner.control({"paused": True})
        self.assertEqual([], self.chores.context(True)["items"])

    def test_multiple_tags_preserve_multiple_room_associations(self):
        inv = self.inventory()
        other = {
            **inv["tags"][0],
            "tag_id": "other-tag",
            "area_id": "hall",
            "room": "Imaginary hall",
        }
        self.areas.inventory = lambda: {"tags": [*inv["tags"], other]}
        self.tags.save(
            {
                "tag_id": "other-tag",
                "name": "Other towels",
                "action": "chore_reminder",
                "chore_id": self.chore["id"],
                "enabled": True,
            }
        )
        self.areas.refresh()
        rooms = self.chores.context(True)["items"][0]["rooms"]
        self.assertEqual({"bath", "hall"}, {r["area_id"] for r in rooms})
        self.assertIn("across rooms", chore_label(self.chores.snapshot()["items"][0]))
        self.tags.remove("other-tag")
        self.assertEqual(1, len(self.chores.snapshot()["items"][0]["rooms"]))

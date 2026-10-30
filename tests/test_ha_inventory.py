"""Synthetic registry fixtures only."""

import unittest
from okabebot.ha_inventory import normalize


class InventoryTests(unittest.TestCase):
    def test_entity_override_device_fallback_and_unavailable(self):
        result = normalize(
            [
                [{"area_id": "study", "name": "Study"}, {"area_id": "hall", "name": "Hall"}],
                [{"id": "device", "area_id": "hall"}],
                [
                    {"entity_id": "sensor.a", "device_id": "device", "area_id": "study"},
                    {"entity_id": "sensor.b", "device_id": "device"},
                    {"entity_id": "sensor.disabled", "disabled_by": "user"},
                ],
                [
                    {
                        "entity_id": "sensor.a",
                        "state": "unavailable",
                        "attributes": {"friendly_name": "<script>"},
                    }
                ],
            ]
        )
        self.assertTrue(result["read_only"])
        self.assertEqual(len(result["entities"]), 2)
        self.assertEqual(result["entities"][0]["room"], "Study")
        self.assertEqual(result["entities"][1]["room"], "Hall")
        self.assertFalse(result["entities"][0]["available"])
        self.assertFalse(result["entities"][1]["available"])
        self.assertNotIn("state", result["entities"][0])

    def test_bindings_keep_ids_across_rename_and_flag_removal(self):
        from tempfile import TemporaryDirectory
        from okabebot.amadeus_feeds import Feeds
        from okabebot.ha_inventory import HomeMap

        with TemporaryDirectory() as folder:
            home = HomeMap(Feeds(folder))
            places = [{"id": "screen-a", "name": "Desk", "approved": True}]
            inventory = {"rooms": [{"id": "area-a", "name": "Study"}], "entities": []}
            home.bind({"location_id": "screen-a", "area_id": "area-a"}, inventory, places)
            renamed = {"rooms": [{"id": "area-a", "name": "Office"}], "entities": []}
            self.assertFalse(home.snapshot(renamed, places)["locations"][0]["needs_review"])
            self.assertTrue(
                home.snapshot({"rooms": [], "entities": []}, places)["locations"][0]["needs_review"]
            )
            with self.assertRaises(ValueError):
                home.bind({"location_id": "unapproved", "area_id": "area-a"}, inventory, places)

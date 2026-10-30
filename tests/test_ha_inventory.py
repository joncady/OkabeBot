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

    def test_floor_registry_renames_and_duplicate_reassignment_keep_stable_ids(self):
        result = normalize(
            [
                [
                    {"area_id": "study", "name": "Study", "floor_id": "upper"},
                    {"area_id": "hall", "name": "Hall", "floor_id": "lower"},
                ],
                [
                    {"id": "device", "area_id": "hall"},
                    {"id": "device", "area_id": "study", "name": "Desk sensor"},
                ],
                [
                    {"entity_id": "sensor.a", "device_id": "device", "area_id": "hall"},
                    {"entity_id": "sensor.a", "device_id": "device"},
                ],
                [
                    {
                        "entity_id": "sensor.a",
                        "state": "on",
                        "attributes": {"private": "not returned"},
                    }
                ],
                [
                    {"floor_id": "upper", "name": "Renamed upstairs"},
                    {"floor_id": "lower", "name": "Ground"},
                ],
            ]
        )
        self.assertTrue(result["floor_registry_available"])
        self.assertEqual(1, len(result["entities"]))
        self.assertEqual("sensor.a", result["entities"][0]["id"])
        self.assertEqual("study", result["entities"][0]["area_id"])
        self.assertEqual("Renamed upstairs", result["entities"][0]["floor"])
        self.assertEqual(["sensor.a"], result["devices"][0]["entity_ids"])
        self.assertNotIn("not returned", str(result))

    def test_removed_and_unassigned_rooms_are_reviewable_without_mutating_bindings(self):
        result = normalize(
            [
                [],
                [{"id": "removed-room-device", "area_id": "removed"}, {"id": "unassigned-device"}],
                [{"entity_id": "sensor.a", "device_id": "removed-room-device"}],
                [],
            ]
        )
        self.assertFalse(result["floor_registry_available"])
        self.assertTrue(result["entities"][0]["needs_review"])
        self.assertTrue(all(d["needs_review"] for d in result["devices"]))
        self.assertEqual("removed", result["entities"][0]["area_id"])
        self.assertEqual([], result["devices"][1]["entity_ids"])


class RegistryTransportTests(unittest.IsolatedAsyncioTestCase):
    async def collect_fixture(self, floor_response):
        from unittest.mock import patch
        from okabebot.ha_inventory import collect

        class Socket:
            def __init__(self):
                self.sent = []
                self.responses = [
                    {"type": "auth_required"},
                    {"type": "auth_ok"},
                    *[{"id": n, "success": True, "result": []} for n in range(1, 5)],
                    floor_response,
                ]

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def receive_json(self):
                return self.responses.pop(0)

            async def send_json(self, data):
                self.sent.append(data)

        socket = Socket()

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def ws_connect(self, *args, **kwargs):
                return socket

        # The HA transport is an optional extra. Test its protocol boundary with a
        # complete fake module so minimal installs never require a real client.
        from types import SimpleNamespace

        transport = SimpleNamespace(
            ClientSession=lambda **kwargs: Session(),
            ClientTimeout=lambda **kwargs: object(),
        )
        with patch.dict("sys.modules", {"aiohttp": transport}):
            result = await collect({"url": "http://ha.example", "token": "invented-test-token"})
        return result, socket.sent

    async def test_supported_floor_registry_is_requested_without_actions(self):
        result, sent = await self.collect_fixture(
            {"id": 5, "success": True, "result": [{"floor_id": "upper", "name": "Upper"}]}
        )
        self.assertEqual("Upper", result["floors"][0]["name"])
        self.assertEqual("config/floor_registry/list", sent[-1]["type"])
        self.assertFalse(any(m.get("type") == "call_service" for m in sent))

    async def test_older_ha_without_floors_keeps_other_registry_coverage(self):
        result, _ = await self.collect_fixture(
            {"id": 5, "success": False, "error": {"code": "unknown_command"}}
        )
        self.assertFalse(result["floor_registry_available"])
        self.assertEqual([], result["floors"])
        self.assertTrue(result["read_only"])

    async def test_mismatched_floor_response_fails_instead_of_claiming_fresh_inventory(self):
        with self.assertRaises(ValueError):
            await self.collect_fixture({"id": 9, "success": True, "result": []})

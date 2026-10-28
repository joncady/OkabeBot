import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from okabebot.config import DEFAULTS
from okabebot.surface_layout import positions, direction
from okabebot.surface_registry import Registry


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = Registry(Path(self.temp.name) / "screens.json")
        self.places = copy.deepcopy(DEFAULTS["surfaces"]["locations"])

    def test_legacy_overlaps_resolve_stably_without_mutating_input(self):
        places = self.places + [{"id": "phone", "adapter": "browser"}]
        saved = {p["id"]: [0, 0] for p in places}
        layout = positions(places, saved)
        self.assertEqual(len({tuple(p) for p in layout.values()}), 3)
        self.assertEqual(layout["companion"], [0, 0])
        self.assertEqual(layout, positions(places, saved))
        self.assertTrue(all(v == [0, 0] for v in saved.values()))

    def test_collision_rejected_and_relative_placement_is_atomic(self):
        self.registry.update(
            "living-room", {"relative_to": "companion", "placement": "up"}, self.places
        )
        before = self.registry.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "occupied"):
            self.registry.update("living-room", {"position": [0, 0]}, self.places)
        self.assertEqual(before, self.registry.path.read_bytes())
        self.assertEqual(self.registry.direction("companion", "living-room", self.places), "up")
        with self.assertRaises(ValueError):
            self.registry.update("living-room", {"position": [0.5, 0]}, self.places)
        self.assertEqual(before, self.registry.path.read_bytes())

    def test_pending_screen_reserves_space_and_relative_reference_is_dynamic(self):
        item = self.registry.register("b" * 64, "Phone", "browser")
        phone = next(p for p in self.registry.enrich(self.places, True) if p["id"] == item["id"])
        with self.assertRaisesRegex(ValueError, "occupied"):
            self.registry.update("living-room", {"position": phone["position"]}, self.places)
        self.registry.update(
            "living-room", {"relative_to": item["id"], "placement": "down"}, self.places
        )
        layout = {p["id"]: p["position"] for p in self.registry.enrich(self.places, True)}
        self.assertEqual(layout["living-room"], [phone["position"][0], phone["position"][1] + 1])

    def test_concurrent_placement_has_only_one_winner(self):
        phone = self.registry.register("c" * 64, "Phone", "browser")

        def place(identity):
            try:
                self.registry.update(identity, {"position": [3, 3]}, self.places)
                return 1
            except ValueError:
                return 0

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(place, ["living-room", phone["id"]])), 1)

    def test_cardinal_directions_are_reciprocal(self):
        for point, forward, reverse in (
            ([-1, 0], "left", "right"),
            ([1, 0], "right", "left"),
            ([0, -1], "up", "down"),
            ([0, 1], "down", "up"),
        ):
            self.assertEqual(direction([0, 0], point), forward)
            self.assertEqual(direction(point, [0, 0]), reverse)
        with self.assertRaises(ValueError):
            direction([0, 0], [0, 0])

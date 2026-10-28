import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from okabebot.config import DEFAULTS
from okabebot.scene_sets import CATALOG, environment
from okabebot.surface_registry import Registry
from okabebot.surfaces import Surfaces
from pi import scene


class SceneWorldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "registry.json"
        self.registry = Registry(self.path)
        self.places = copy.deepcopy(DEFAULTS["surfaces"]["locations"])

    def assign(self, location, selected, character="okabe"):
        self.registry.update(location, {"scene_selections": {character: selected}}, self.places)

    def test_catalog_has_two_sets_per_character_and_pi_supports_all(self):
        for choices in CATALOG["characters"].values():
            self.assertEqual(len(choices), 2)
            self.assertTrue(all(c in CATALOG["sets"] for c in choices))
        self.assertEqual(set(CATALOG["sets"]), set(scene.scene_sets.SETS))

    def test_unique_across_presentations_persistent_and_explicit_release(self):
        self.assign("companion", "pixel-lab")
        self.registry.update("living-room", {"presentation": "room"}, self.places)
        with self.assertRaisesRegex(ValueError, "belongs"):
            self.assign("living-room", "pixel-lab")
        self.assign("living-room", "maid-cafe")
        self.assertEqual(
            Registry(self.path).enrich(self.places)[1]["scene_selections"]["okabe"], "maid-cafe"
        )
        self.assign("companion", None)
        self.assign("living-room", "pixel-lab")
        self.assertTrue(self.registry.scene_world_enabled())

    def test_concurrent_claim_has_only_one_owner(self):
        def assign(location):
            try:
                self.assign(location, "pixel-lab")
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(assign, ["companion", "living-room"])), 1)

    def test_wrong_character_and_presentation_rejected_without_disk_mutation(self):
        for values in (
            {"scene_selections": {"sonic": "maid-cafe"}},
            {"presentation": "unknown"},
            {"presentation": "room"},
        ):
            with self.assertRaises(ValueError):
                self.registry.update("companion", values, self.places)
        self.assertFalse(self.path.exists())

    def test_unassigned_target_and_home_block_before_hardware(self):
        self.assign("companion", "pixel-lab")
        with patch("okabebot.surface_registry.registry_path", return_value=self.path):
            surfaces = Surfaces(Mock(), start=False)
            with self.assertRaisesRegex(ValueError, "Assign"):
                surfaces.move("living-room", "http://controller")
            with self.assertRaises(ValueError):
                surfaces.ensure_scene("companion", "kurisu")
            surfaces.rpc.assert_not_called()
            self.assign("companion", None)
            with self.assertRaises(ValueError):
                surfaces.return_home()
            surfaces.rpc.assert_not_called()

    def test_initialization_is_atomic_complete_and_not_repeatable(self):
        self.registry.initialize_scenes(self.places)
        data = self.registry.read()
        self.assertTrue(data["scene_world_enabled"])
        self.assertEqual(set(data["scenes"]["companion"]), set(CATALOG["characters"]))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already initialized"):
            self.registry.initialize_scenes(self.places)
        self.assertEqual(before, self.path.read_bytes())

    def test_setup_and_edits_preserve_home_and_occupied_set(self):
        with (
            patch("okabebot.surface_registry.registry_path", return_value=self.path),
            patch("okabebot.profiles.current_character", return_value={"style": "okabe"}),
        ):
            surfaces = Surfaces(Mock(), start=False)
            surfaces.layout({"initialize_scenes": True})
            before = self.path.read_bytes()
            for change, message in (
                ({"okabe": None}, "Keep a home"),
                ({"okabe": "maid-cafe"}, "Move the character"),
            ):
                with self.assertRaisesRegex(ValueError, message):
                    surfaces.layout({"id": "companion", "scene_selections": change})
                self.assertEqual(before, self.path.read_bytes())
            surfaces.layout({"id": "living-room", "scene_selections": {"okabe": "maid-cafe"}})
            surfaces.ensure_scene("living-room", "okabe")
            surfaces.phase = "leaving_pi"
            with self.assertRaisesRegex(ValueError, "finish moving"):
                surfaces.layout({"id": "living-room", "scene_selections": {"okabe": None}})
            surfaces.rpc.assert_not_called()

    def test_setup_rejected_while_away_or_combined_with_other_edits(self):
        with patch("okabebot.surface_registry.registry_path", return_value=self.path):
            surfaces = Surfaces(Mock(), start=False)
            with self.assertRaisesRegex(ValueError, "other layout"):
                surfaces.layout({"initialize_scenes": True, "id": "companion"})
            surfaces.phase = "tv"
            with self.assertRaisesRegex(ValueError, "Return the character"):
                surfaces.layout({"initialize_scenes": True})
            self.assertFalse(self.path.exists())

    def test_away_assignment_without_home_cannot_depart(self):
        self.assign("living-room", "maid-cafe")
        with patch("okabebot.surface_registry.registry_path", return_value=self.path):
            surfaces = Surfaces(Mock(), start=False)
            with self.assertRaisesRegex(ValueError, "home scene"):
                surfaces.ensure_scene("living-room", "okabe")
            surfaces.rpc.assert_not_called()

    def test_legacy_is_explicit_and_pi_unassigned_hides_character(self):
        place = self.registry.enrich(self.places)[0]
        self.assertFalse(self.registry.scene_world_enabled())
        self.assertTrue(environment(place, "okabe", False)["assigned"])
        self.assertFalse(environment(place, "okabe", True)["assigned"])
        shapes = scene.shapes(style="okabe", environment="unassigned")
        self.assertEqual(len(shapes), 1)
        for selected in CATALOG["sets"]:
            self.assertTrue(scene.render(style="okabe", environment=selected).getbbox())

"""No hardware: discovery, approval, revocation, spatial routing and handoffs."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from okabebot.config import DEFAULTS
from okabebot.surface_registry import Registry
from okabebot.surfaces import Surfaces


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "registry.json"
        self.registry = Registry(self.path)
        self.places = copy.deepcopy(DEFAULTS["surfaces"]["locations"])
        self.secret = "a" * 64

    def test_first_visit_pending_stable_identity_and_no_secret_on_disk(self):
        a = self.registry.register(self.secret, "Phone", "browser")
        b = self.registry.register(self.secret, "Different label", "browser")
        self.assertEqual(a["id"], b["id"])
        self.assertFalse(a["approved"])
        self.assertNotIn(self.secret, self.path.read_text())
        with self.assertRaises(PermissionError):
            self.registry.device(self.secret)
        self.assertEqual(len(self.registry.enrich(self.places)), 2)
        self.assertEqual(len(self.registry.enrich(self.places, True)), 3)

    def test_approval_revocation_and_persistent_layout(self):
        item = self.registry.register(self.secret, "Phone", "browser")
        self.registry.update(item["id"], {"approved": True, "position": [-3, 1]}, self.places)
        self.assertEqual(self.registry.device(self.secret)["id"], item["id"])
        self.assertEqual(Registry(self.path).enrich(self.places)[-1]["position"], [-3, 1])
        self.assertEqual(self.registry.direction("companion", item["id"], self.places), "left")
        self.registry.update(item["id"], {"position": [0, -2]}, self.places)
        self.assertEqual(self.registry.direction("companion", item["id"], self.places), "up")
        self.registry.update(item["id"], {"approved": False}, self.places)
        with self.assertRaises(PermissionError):
            self.registry.device(self.secret)

    def test_invalid_and_ambiguous_layout_rejected(self):
        for position in ([float("nan"), 0], [20, 0], [True, 0], [0]):
            with self.assertRaises(ValueError):
                self.registry.update("companion", {"position": position}, self.places)
        with self.assertRaises(ValueError):
            self.registry.update("companion", {"name": "Living room TV"}, self.places)

    def test_renames_use_persisted_names_and_preserve_rejected_state(self):
        self.registry.update("companion", {"name": "Desk"}, self.places)
        before = self.path.read_bytes()
        for name in ("Desk", "desk", "  DESK  "):
            with self.assertRaisesRegex(ValueError, "unique"):
                Registry(self.path).update("living-room", {"name": name}, self.places)
            self.assertEqual(self.path.read_bytes(), before)
        phone = self.registry.register(self.secret, "Phone", "browser")
        with self.assertRaisesRegex(ValueError, "unique"):
            self.registry.update(phone["id"], {"name": "Desk"}, self.places)
        self.registry.update("companion", {"name": "Studio"}, self.places)
        self.registry.update("living-room", {"name": "Desk"}, self.places)
        self.assertEqual([p["name"] for p in self.registry.enrich(self.places)], ["Studio", "Desk"])

    def test_browser_handoff_waits_for_render_and_cannot_ack_other_device(self):
        with patch("okabebot.surface_registry.registry_path", return_value=self.path):
            surface = Surfaces(Mock(), start=False)
            item = surface.registry.register(self.secret, "Phone", "browser")
            surface.registry.update(item["id"], {"approved": True}, self.places)
            surface.move(item["id"], "http://controller")
            self.assertEqual(surface.phase, "preparing")
            surface.tick()
            surface.rpc.assert_not_called()
            surface.heartbeat(self.secret)
            surface.tick()
            self.assertEqual(surface.phase, "leaving_pi")
            surface.rpc.return_value = {
                "presence": {"transition_id": surface.identifier, "rendered": "away"}
            }
            surface.tick()
            self.assertEqual(surface.phase, "entering_tv")
            surface.acknowledge(self.secret, "entered", surface.identifier)
            self.assertEqual(surface.snapshot()["current_location"], item["id"])
            other = surface.registry.register("b" * 64, "Mac", "mac")
            surface.registry.update(other["id"], {"approved": True}, self.places)
            with self.assertRaises(PermissionError):
                surface.acknowledge("b" * 64, "departed", surface.identifier)
            self.assertEqual(surface.view("b" * 64, {})["phase"], "idle")
            surface.registry.update(item["id"], {"approved": False}, self.places)
            self.assertFalse(surface.authorized(self.secret))

    def test_location_audio_selection_is_persistent_and_bounded(self):
        item = self.registry.register(self.secret, "Phone", "browser")
        self.registry.update(item["id"], {"approved": True, "audio_target": "pi"}, self.places)
        self.assertEqual(Registry(self.path).enrich(self.places)[-1]["audio_target"], "pi")
        with self.assertRaises(ValueError):
            self.registry.update(item["id"], {"audio_target": "arbitrary-url"}, self.places)
        with self.assertRaises(ValueError):
            self.registry.update("companion", {"audio_target": "device"}, self.places)

    def test_schema_is_json_safe(self):
        self.registry.register(self.secret, "Phone", "browser")
        json.dumps(self.registry.enrich(self.places, True), allow_nan=False)

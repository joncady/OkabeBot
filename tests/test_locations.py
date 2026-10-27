import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from okabebot.config import DEFAULTS, load
from okabebot import locations
from okabebot.local_conversation import shortlist, validate_call
from okabebot.surfaces import Surfaces

CUSTOM = [
    {"id": "desk-nook", "name": "Desk nook", "aliases": ["my desk"], "adapter": "pi"},
    {"id": "den-screen", "name": "Den screen", "aliases": ["cinema"], "adapter": "cast"},
]


class LocationTests(unittest.TestCase):
    def settings(self, places):
        value = copy.deepcopy(DEFAULTS["surfaces"])
        value["locations"] = places
        return value

    def test_arbitrary_labels_and_ids_reach_the_correct_adapter(self):
        config = copy.deepcopy(DEFAULTS)
        config["surfaces"] = self.settings(CUSTOM)
        with patch("okabebot.config.get_config", return_value=config):
            s = Surfaces(Mock(), start=False)
            self.assertEqual(s.snapshot()["current_location"], "desk-nook")
            with patch.object(
                s, "begin", return_value={"phase": "preparing", "url": "private"}
            ) as begin:
                result = s.move("den-screen", "http://test")
            begin.assert_called_once_with("http://test")
            self.assertNotIn("url", result)
            self.assertTrue(result["accepted"])
            self.assertTrue(s.move("desk-nook", "http://test")["already_there"])
            with self.assertRaises(ValueError):
                s.move("shelf", "http://test")

    def test_ambiguous_aliases_and_unsupported_adapters_rejected_at_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for places in [
                CUSTOM + CUSTOM[:1],
                [CUSTOM[0], dict(CUSTOM[1], aliases=["my desk"])],
                [dict(CUSTOM[0], adapter="unknown"), CUSTOM[1]],
            ]:
                path.write_text(json.dumps({"surfaces": {"locations": places}}))
                with self.assertRaises(ValueError):
                    load(path)

    def test_voice_destination_is_grounded_in_config_not_model_guess(self):
        specs = {
            "move_companion": {
                "parameters": {
                    "type": "object",
                    "properties": {"location_id": {"type": "string"}},
                    "required": ["location_id"],
                }
            },
            "get_companion_locations": {},
        }
        policy = {"auto_approve_hardware": True, "allowed_tools": ["move_companion"]}
        with patch("okabebot.locations.configured", return_value=copy.deepcopy(CUSTOM)):
            self.assertEqual(locations.destination("Move from my desk to cinema"), "den-screen")
            self.assertEqual(shortlist("Come to my desk", specs), ["move_companion"])
            self.assertEqual(
                validate_call(
                    "Go to cinema",
                    {"name": "move_companion", "arguments": {"location_id": "den-screen"}},
                    specs,
                    policy,
                    "id",
                )[1],
                {"location_id": "den-screen"},
            )
            for text, identity in [
                ("Go to cinema", "desk-nook"),
                ("Do not go to cinema", "den-screen"),
                ("What would happen if you go to cinema?", "den-screen"),
                ("Move to the kitchen", "den-screen"),
            ]:
                with self.subTest(text=text), self.assertRaises(ValueError):
                    validate_call(
                        text,
                        {"name": "move_companion", "arguments": {"location_id": identity}},
                        specs,
                        policy,
                        "id",
                    )
            self.assertIsNone(locations.destination("my desk or cinema"))

    def test_input_is_scoped_bounded_and_reports_only_supported_keys(self):
        s = Surfaces(Mock(), start=False)
        s.preview("http://test")
        with self.assertRaises(PermissionError):
            s.input(s.preview_token, "Enter")
        s.begin("http://test", launch=False)
        self.assertTrue(s.input(s.token, "Enter")["accepted"])
        self.assertEqual(s.snapshot()["remote_input"]["key"], "Enter")
        with self.assertRaises(ValueError):
            s.input(s.token, "secret text")

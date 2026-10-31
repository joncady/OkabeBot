"""Synthetic worker schema transitions; no model or device dependencies."""

import copy
import unittest

from okabebot.local_worker import request_tools


class RequestToolsTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            name: {"type": "function", "function": {"name": name, "parameters": {}}}
            for name in ("move_companion", "get_current_media")
        }

    def test_read_only_null_override_cannot_poison_next_request(self):
        original = copy.deepcopy(self.base)
        names, tools = request_tools(
            self.base,
            {
                "tool_names": ["get_current_media"],
                "location_tool": {"type": "function", "function": None},
            },
        )
        self.assertEqual(names, ("get_current_media",))
        self.assertEqual(tools, [self.base["get_current_media"]])
        _, later = request_tools(self.base, {"tool_names": list(self.base)})
        self.assertTrue(all(isinstance(t["function"], dict) for t in later))
        self.assertEqual(self.base, original)

    def test_valid_dynamic_override_is_request_local_and_respects_allowlist(self):
        override = copy.deepcopy(self.base["move_companion"])
        override["function"]["parameters"] = {"enum": ["invented desk"]}
        _, tools = request_tools(
            self.base, {"tool_names": ["move_companion"], "location_tool": override}
        )
        self.assertEqual(tools, [override])
        _, next_tools = request_tools(self.base, {"tool_names": ["move_companion"]})
        self.assertEqual(next_tools, [self.base["move_companion"]])
        _, read_only = request_tools(
            self.base, {"tool_names": ["get_current_media"], "location_tool": override}
        )
        self.assertEqual(read_only, [self.base["get_current_media"]])

    def test_malformed_or_other_function_cannot_replace_location(self):
        for value in (None, "bad", {}, {"function": None}, self.base["get_current_media"]):
            with self.subTest(value=value):
                _, tools = request_tools(
                    self.base, {"tool_names": ["move_companion"], "location_tool": value}
                )
                self.assertEqual(tools, [self.base["move_companion"]])

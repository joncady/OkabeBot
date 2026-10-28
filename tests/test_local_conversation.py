import threading
import unittest
from unittest.mock import Mock, patch
from okabebot.local_conversation import validate_call, LocalConversation

SPECS = {
    "set_speaker_volume": {
        "parameters": {
            "type": "object",
            "properties": {"percent": {"type": "integer"}},
            "required": ["percent"],
        }
    },
    "press_bot": {
        "parameters": {
            "type": "object",
            "properties": {"request_id": {"type": "string"}},
            "required": ["request_id"],
        }
    },
    "get_current_media": {"parameters": {"type": "object", "properties": {}}},
}
POLICY = {"auto_approve_hardware": True, "allowed_tools": list(SPECS)}


class LocalToolTests(unittest.TestCase):
    def test_explicit_action_arguments_and_application_owned_request_id(self):
        name, args = validate_call(
            "Wave with SwitchBot",
            {"name": "press_bot", "arguments": {"request_id": "model-reused-id"}},
            SPECS,
            POLICY,
            "actual-request-id",
        )
        self.assertEqual(name, "press_bot")
        self.assertEqual(args, {"request_id": "actual-request-id"})
        self.assertEqual(
            validate_call(
                "Set speaker volume to 5 percent",
                {"name": "set_speaker_volume", "arguments": {"percent": 5}},
                SPECS,
                POLICY,
                "id",
            )[1],
            {"percent": 5},
        )

    def test_ambiguous_unrelated_negated_and_explanatory_actions_are_blocked(self):
        for text in [
            "Turn it off",
            "Turn off the kitchen lights",
            "Do not press SwitchBot",
            "How does pressing SwitchBot work?",
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_call(text, {"name": "press_bot", "arguments": {}}, SPECS, POLICY, "unique")

    def test_bad_arguments_unknown_tools_and_disabled_actions_are_blocked(self):
        for call in [
            {"name": "shell", "arguments": {}},
            {"name": "set_speaker_volume", "arguments": {"percent": True}},
            {"name": "set_speaker_volume", "arguments": {"percent": 50}},
            {"name": "set_speaker_volume", "arguments": {"percent": 5, "path": "other"}},
        ]:
            with self.subTest(call=call), self.assertRaises(ValueError):
                validate_call("Set speaker volume to 5 percent", call, SPECS, POLICY, "id")
        with self.assertRaises(ValueError):
            validate_call(
                "Wave",
                {"name": "press_bot", "arguments": {}},
                SPECS,
                dict(POLICY, auto_approve_hardware=False),
                "id",
            )

    def adapter(self, output):
        obj = LocalConversation.__new__(LocalConversation)
        obj.process = Mock()
        obj.cancelled = threading.Event()
        obj.lock = threading.RLock()
        obj.busy = True
        obj.notify = Mock()
        obj.completed = Mock()
        obj.specs = SPECS
        obj.policy = POLICY
        obj._read = Mock(return_value={"text": output, "selection_s": 0.5})
        return obj

    @patch("okabebot.server.set_speaker_volume")
    def test_real_adapter_calls_tool_once_then_acknowledges_confirmed_result(self, volume):
        volume.return_value = {"percent": 5}
        obj = self.adapter(
            '<tool_call>{"name":"set_speaker_volume","arguments":{"percent":5}}</tool_call>'
        )
        obj._turn("Set speaker volume to 5 percent")
        volume.assert_called_once_with(percent=5)
        obj.completed.assert_called_once_with("Speaker volume is now 5 percent.", "completed")
        self.assertFalse(obj.busy)

    @patch("okabebot.server.press_bot")
    def test_ambiguous_actual_adapter_cannot_execute(self, press):
        obj = self.adapter('<tool_call>{"name":"press_bot","arguments":{}}</tool_call>')
        obj._turn("Turn it off")
        press.assert_not_called()
        self.assertIn("Which device", obj.completed.call_args.args[0])

    @patch("okabebot.server.get_companion_locations")
    def test_destination_discovery_uses_live_registry_without_model_paraphrase(self, locations):
        import copy

        locations.return_value = {"locations": [{"name": "Desk"}, {"name": "TV"}]}
        obj = self.adapter("I can help you locate screens.")
        obj.specs = copy.deepcopy(SPECS)
        obj.specs["get_companion_locations"] = {"parameters": {"type": "object", "properties": {}}}
        obj._turn("Which screens can you go to?")
        locations.assert_called_once_with()
        obj._read.assert_not_called()
        obj.process.stdin.write.assert_not_called()
        obj.completed.assert_called_once_with("My destinations are Desk, TV.", "completed")

    @patch("okabebot.server.set_speaker_volume", side_effect=TimeoutError())
    def test_unknown_action_outcome_is_not_retried_or_acknowledged_as_success(self, volume):
        obj = self.adapter(
            '<tool_call>{"name":"set_speaker_volume","arguments":{"percent":5}}</tool_call>'
        )
        obj._turn("Set speaker volume to 5 percent")
        self.assertEqual(volume.call_count, 1)
        obj.completed.assert_not_called()
        self.assertEqual(obj.notify.call_args.args[1]["status"], "failed")

    @patch("okabebot.server.set_speaker_volume")
    def test_cancel_before_generation_returns_prevents_action(self, volume):
        obj = self.adapter(
            '<tool_call>{"name":"set_speaker_volume","arguments":{"percent":5}}</tool_call>'
        )
        obj.cancelled.set()
        obj._turn("Set speaker volume to 5 percent")
        volume.assert_not_called()
        obj.completed.assert_not_called()
        self.assertEqual(obj.notify.call_args.args[1]["status"], "cancelled")

    @patch("okabebot.server.set_speaker_volume")
    def test_unstructured_claim_does_not_confirm_unexecuted_action(self, volume):
        obj = self.adapter("Done, your volume is five percent.")
        obj._turn("Set speaker volume to 5 percent")
        volume.assert_not_called()
        self.assertIn("Which device", obj.completed.call_args.args[0])


class LocationAcknowledgementTests(unittest.TestCase):
    def test_real_tool_response_lists_names_and_handles_empty_registry(self):
        from okabebot.local_conversation import acknowledgement
        from okabebot.server import get_companion_locations

        for places, expected in (
            ([{"name": "Desk"}, {"name": "TV"}], "My destinations are Desk, TV."),
            ([], "I have no configured destinations."),
        ):
            with patch(
                "okabebot.controller_tools.projection",
                return_value={
                    "surfaces": {
                        "locations": places,
                        "current_location": None,
                        "destination_location": None,
                        "destination_name": "",
                        "phase": "pi",
                    }
                },
            ):
                result = get_companion_locations()
            self.assertEqual(acknowledgement("get_companion_locations", result), expected)

import json
import unittest
from unittest.mock import patch

from okabebot.http_worker import decode_message
import test_local_conversation as local_tests


class StructuredCallTests(unittest.TestCase):
    def message(self, arguments):
        return {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {"name": "set_speaker_volume", "arguments": arguments},
                }
            ]
        }

    def test_native_arguments_are_decoded_without_model_markup(self):
        for args in ({"percent": 5}, json.dumps({"percent": 5})):
            self.assertEqual(
                decode_message(self.message(args))["tool_call"],
                {"name": "set_speaker_volume", "arguments": {"percent": 5}},
            )

    def test_multiple_calls_non_object_and_unparsed_markup_rejected(self):
        multiple = self.message({})
        multiple["tool_calls"] *= 2
        for message in (
            multiple,
            self.message("[]"),
            self.message("{bad"),
            {"content": '<tool_call>{"name":"press_bot"}</tool_call>'},
        ):
            with self.subTest(message=message), self.assertRaises(ValueError):
                decode_message(message)

    @patch("okabebot.server.set_speaker_volume")
    def test_structured_call_uses_existing_validation_and_one_dispatch(self, volume):
        volume.return_value = {"percent": 5}
        obj = local_tests.LocalToolTests().adapter("Unused text")
        obj._read.return_value = dict(decode_message(self.message({"percent": 5})), selection_s=0.2)
        obj._turn("Set speaker volume to 5 percent")
        volume.assert_called_once_with(percent=5)

    @patch("okabebot.server.set_speaker_volume")
    def test_structured_call_cannot_bypass_unknown_argument_guard(self, volume):
        obj = local_tests.LocalToolTests().adapter("")
        obj._read.return_value = dict(
            decode_message(self.message({"percent": 5, "id": "bad"})), selection_s=0.2
        )
        obj._turn("Set speaker volume to 5 percent")
        volume.assert_not_called()

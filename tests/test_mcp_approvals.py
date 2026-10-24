import threading
import unittest
from unittest.mock import Mock
from okabebot.codex import Codex


class McpApprovalTests(unittest.TestCase):
    def client(self, modes=None):
        c = Codex.__new__(Codex)
        c.lock = threading.RLock()
        c.send = Mock()
        c.approvals = {
            "4": {
                "id": 4,
                "method": "mcpServer/elicitation/request",
                "params": {
                    "mode": "form",
                    "serverName": "hardware-lab",
                    "_meta": {"codex_approval_kind": "mcp_tool_call", "persist": modes or []},
                    "requestedSchema": {"type": "object", "properties": {}},
                },
            }
        }
        return c

    def test_session_grant_uses_native_metadata(self):
        c = self.client(["session", "always"])
        c.answer("4", "accept", persist="session")
        c.send.assert_called_once_with(
            {
                "id": 4,
                "result": {"action": "accept", "content": {}, "_meta": {"persist": "session"}},
            }
        )
        self.assertEqual(c.approvals, {})

    def test_once_does_not_persist(self):
        c = self.client(["session"])
        c.answer("4", "accept")
        self.assertIsNone(c.send.call_args.args[0]["result"]["_meta"])

    def test_decline_has_no_content(self):
        c = self.client()
        c.answer("4", "decline")
        self.assertEqual(
            c.send.call_args.args[0]["result"],
            {"action": "decline", "content": None, "_meta": None},
        )

    def test_unoffered_or_permanent_scope_rejected(self):
        for modes, scope in [([], "session"), (["session", "always"], "always")]:
            c = self.client(modes)
            with self.assertRaises(ValueError):
                c.answer("4", "accept", persist=scope)
            c.send.assert_not_called()
            self.assertIn("4", c.approvals)

    def test_generic_form_cannot_be_blindly_accepted(self):
        c = self.client()
        c.approvals["4"]["params"]["requestedSchema"]["properties"] = {"name": {"type": "string"}}
        with self.assertRaises(ValueError):
            c.answer("4", "accept")
        c.send.assert_not_called()

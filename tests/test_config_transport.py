from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from okabebot.config import DEFAULTS, load
from okabebot.transport import Device
from okabebot import approvals


class ConfigTests(unittest.TestCase):
    def config(self, data):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        path.write_text(json.dumps(data))
        return load(path)

    def test_defaults_are_local_okabe_and_scoped_auto_approval(self):
        c = self.config({})
        self.assertEqual(c["character"]["name"], "Okabe")
        self.assertEqual(c["devices"]["voice"]["transport"], "local")
        self.assertTrue(c["approvals"]["auto_approve_hardware"])
        self.assertIn("press_bot", c["approvals"]["allowed_tools"])
        self.assertTrue(Path(c["state_dir"]).is_absolute())

    def test_partial_override_preserves_other_defaults(self):
        c = self.config(
            {"character": {"name": "Dot"}, "approvals": {"auto_approve_hardware": False}}
        )
        self.assertEqual(c["character"]["name"], "Dot")
        self.assertEqual(c["character"]["default_voice"], "calm")
        self.assertFalse(c["approvals"]["auto_approve_hardware"])

    def test_bad_keys_and_types_fail_early(self):
        for data in [
            {"typo": True},
            {"web": {"port": True}},
            {"approvals": {"auto_approve_hardware": "false"}},
            {"character": {"palette": {"accent": "red"}}},
            {"devices": {"voice": {"transport": "ssh", "ssh_target": "-bad"}}},
        ]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.config(data)


class TransportTests(unittest.TestCase):
    def test_single_pi_does_not_launch_ssh(self):
        d = Device(deepcopy(DEFAULTS["devices"]["voice"]))
        with (
            patch("okabebot.transport.http_rpc", return_value={"ok": True}) as http,
            patch("okabebot.transport.subprocess.Popen") as popen,
        ):
            self.assertEqual(d.rpc({"op": "status"}), {"ok": True})
            with d.connect() as rpc:
                rpc({"op": "events"})
            popen.assert_not_called()
            self.assertEqual(http.call_count, 2)

    def test_remote_rpc_quotes_paths_and_does_not_retry(self):
        config = deepcopy(DEFAULTS["devices"]["voice"])
        config.update(transport="ssh", ssh_target="pi@voice.local", remote_dir="/opt/my lab/pi")
        d = Device(config)
        with patch(
            "okabebot.transport.subprocess.run",
            return_value=Mock(returncode=0, stdout='{"ok":true}'),
        ) as run:
            self.assertEqual(d.rpc({"op": "status"}), {"ok": True})
            self.assertIn("'/opt/my lab/pi/bridge.py'", run.call_args.args[0][-1])
            run.assert_called_once()


class AutomaticApprovalTests(unittest.TestCase):
    def request(self):
        return {
            "id": 1,
            "method": "mcpServer/elicitation/request",
            "params": {
                "serverName": "hardware-lab",
                "mode": "form",
                "message": 'Allow the hardware-lab MCP server to run tool "press_bot"?',
                "_meta": {"codex_approval_kind": "mcp_tool_call", "persist": ["session"]},
                "requestedSchema": {"type": "object", "properties": {}},
            },
        }

    def test_requested_hardware_automatically_approved_once(self):
        result = approvals.automatic_response(self.request(), DEFAULTS["approvals"])
        self.assertEqual(result, {"action": "accept", "content": {}, "_meta": None})

    def test_disable_or_remove_tool_requires_manual_approval(self):
        for policy in [
            {"auto_approve_hardware": False, "allowed_tools": ["press_bot"]},
            {"auto_approve_hardware": True, "allowed_tools": []},
        ]:
            self.assertIsNone(approvals.automatic_response(self.request(), policy))

    def test_other_servers_commands_forms_and_denials_never_autoapprove(self):
        changes = [
            ("serverName", "other"),
            ("mode", "url"),
            ("requestedSchema", {"type": "object", "properties": {"password": {"type": "string"}}}),
            ("message", 'Allow the hardware-lab MCP server to run tool "unknown"?'),
        ]
        for key, value in changes:
            r = self.request()
            r["params"][key] = value
            self.assertIsNone(approvals.automatic_response(r, DEFAULTS["approvals"]))
        r = self.request()
        r["params"]["_meta"]["review_denied"] = True
        self.assertIsNone(approvals.automatic_response(r, DEFAULTS["approvals"]))
        r = self.request()
        r["method"] = "item/commandExecution/requestApproval"
        self.assertIsNone(approvals.automatic_response(r, DEFAULTS["approvals"]))


class LocalHttpTests(unittest.TestCase):
    def test_local_rpc_and_tunnel_interface_use_same_protocol(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"received": payload, "path": self.path}).encode())

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            config = deepcopy(DEFAULTS["devices"]["voice"])
            config["port"] = server.server_port
            d = Device(config)
            payload = {"op": "status"}
            expected = {"received": payload, "path": "/rpc"}
            self.assertEqual(d.rpc(payload), expected)
            with d.connect() as rpc:
                self.assertEqual(rpc(payload), expected)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

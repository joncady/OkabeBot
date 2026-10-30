import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import Mock, patch
from okabebot import ha_companion, ha_satellite


class Stop:
    def __init__(self):
        self.done = False

    def is_set(self):
        return self.done

    def wait(self, seconds):
        self.done = True
        return True


class RecoveryTests(unittest.TestCase):
    def run_adapter(self, module, online, state=None):
        client = Mock()
        client.is_connected.return_value = online
        mqtt = ModuleType("paho.mqtt")
        mqtt.client = SimpleNamespace(
            Client=Mock(return_value=client), CallbackAPIVersion=SimpleNamespace(VERSION2=2)
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            control = root / "control.json"
            control.write_text(json.dumps({"url": "http://localhost:9/#synthetic-token"}))
            cfg = root / "bridge.json"
            cfg.write_text(
                json.dumps(
                    {
                        "id": "fixture",
                        "name": "Fixture",
                        "area": "Office",
                        "host": "localhost",
                        "username": "fixture",
                        "password": "invented",
                        "location_id": "desk",
                        "control_file": str(control),
                        "ssh_argv": ["never-execute"],
                    }
                )
            )
            response = Mock()
            response.__enter__ = Mock(return_value=io.BytesIO(json.dumps(state or {}).encode()))
            response.__exit__ = Mock(return_value=False)
            with (
                patch.dict(sys.modules, {"paho.mqtt": mqtt}),
                patch.object(sys, "argv", ["adapter", "--config", str(cfg)]),
                patch("urllib.request.urlopen", return_value=response) as request,
                patch("subprocess.run", side_effect=AssertionError("Hardware access forbidden")),
            ):
                module.run(Stop())
        return client, request

    def test_offline_start_waits_for_reconnect_without_probing_or_queueing(self):
        for module in (ha_companion, ha_satellite):
            with self.subTest(module=module.__name__):
                client, request = self.run_adapter(module, False)
                client.connect_async.assert_called_once()
                client.connect.assert_not_called()
                client.publish.assert_not_called()
                request.assert_not_called()
                client.disconnect.assert_called_once()
                client.loop_stop.assert_called_once()

    def test_connected_projection_excludes_private_content_and_shutdown_completes(self):
        client, request = self.run_adapter(
            ha_companion,
            True,
            {
                "character": "Fixture",
                "busy": False,
                "recording": False,
                "messages": ["private synthetic transcript"],
                "notifications": ["synthetic inbox"],
                "preferences": {"secret": "synthetic"},
                "status": "untrusted arbitrary text",
                "speaker_volume": {"percent": 22},
                "device_health": {},
            },
        )
        projection = next(
            json.loads(call.args[1])
            for call in client.publish.call_args_list
            if call.args[0].endswith("/state")
        )
        self.assertEqual(
            set(projection),
            {
                "character",
                "busy",
                "recording",
                "status",
                "volume",
                "voice_connected",
                "display_connected",
                "mac_screen",
                "distance_mm",
                "temperature_c",
                "humidity_percent",
                "tilt_closed",
                "nearby",
            },
        )
        self.assertEqual(projection["status"], "idle")
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()

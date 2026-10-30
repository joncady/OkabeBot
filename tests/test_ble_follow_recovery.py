import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError
from okabebot import ble_follow
from tests.test_mqtt_recovery import Stop


class FollowRecoveryTests(unittest.TestCase):
    def test_controller_outage_pauses_without_moving_and_reaps_both_scanners(self):
        client = Mock()
        paho = ModuleType("paho")
        mqtt = ModuleType("paho.mqtt")
        paho.mqtt = mqtt
        mqtt.client = SimpleNamespace(
            Client=Mock(return_value=client), CallbackAPIVersion=SimpleNamespace(VERSION2=2)
        )
        processes = [Mock(stdout=[]) for _ in range(2)]
        for process in processes:
            process.poll.return_value = None
        response = Mock()
        response.__enter__ = Mock(
            return_value=io.BytesIO(
                json.dumps({"surfaces": {"locations": [{"id": "down"}, {"id": "up"}]}}).encode()
            )
        )
        response.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "control.json").write_text(json.dumps({"url": "http://localhost:9/#synthetic"}))
            cfg = root / "follow.json"
            cfg.write_text(
                json.dumps(
                    {
                        "host": "localhost",
                        "username": "fixture",
                        "password": "invented",
                        "body_topic": "fixture/body",
                        "beacon": {},
                        "control_file": str(root / "control.json"),
                        "require_worn": False,
                        "anchors": [
                            {"location_id": place, "scanner_argv": ["fake-scanner"]}
                            for place in ("down", "up")
                        ],
                    }
                )
            )
            with (
                patch.dict(
                    sys.modules, {"paho": paho, "paho.mqtt": mqtt, "paho.mqtt.client": mqtt.client}
                ),
                patch.object(sys, "argv", ["follow", "--config", str(cfg), "--seconds", "60"]),
                patch("subprocess.Popen", side_effect=processes),
                patch(
                    "urllib.request.urlopen", side_effect=[response, URLError("offline")]
                ) as http,
            ):
                ble_follow.run(Stop())
            self.assertEqual(http.call_count, 2)
            self.assertTrue(all(call.args[0].data is None for call in http.call_args_list))
            for process in processes:
                process.terminate.assert_called_once()
                process.wait.assert_called_once()
            client.disconnect.assert_called_once()
            client.loop_stop.assert_called_once()

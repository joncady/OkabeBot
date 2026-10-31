import json
import subprocess
import sys
import unittest
from okabebot.ha_satellite import PROBE, discovery, room_values
from okabebot.ha_companion import room_discovery


class SatelliteTests(unittest.TestCase):
    def test_optional_room_projection_and_discovery_never_invent_hardware(self):
        self.assertTrue(all(v is None for v in room_values({}).values()))
        values = room_values(
            {
                "room_sensors": {
                    "connected": True,
                    "temperature_c": 20,
                    "humidity_percent": float("nan"),
                    "button_pressed": False,
                    "distance_mm": True,
                    "tilt_closed": True,
                }
            }
        )
        self.assertEqual(
            values,
            {
                "temperature_c": 20,
                "humidity_percent": None,
                "button_pressed": False,
                "distance_mm": None,
            },
        )
        fields = [k for k, v in values.items() if v is not None]
        configs = list(room_discovery("lab/test", "test", "Test", "Study", fields=fields))
        self.assertEqual(len(configs), 2)
        self.assertFalse(any("tilt" in topic for topic, _ in configs))
        for _, config in configs:
            self.assertNotIn("command_topic", config)
            self.assertEqual(config["expire_after"], 45)
        offline = room_values({"room_sensors": {"connected": False, "temperature_c": 20}})
        self.assertIsNone(offline["temperature_c"])

    def test_grouped_read_only_entities(self):
        configs = list(discovery("lab/anchor", "anchor", "Anchor", "Office"))
        self.assertEqual(len(configs), 4)
        for topic, config in configs:
            self.assertEqual(config["device"]["suggested_area"], "Office")
            self.assertNotIn("command_topic", config)
            self.assertEqual(config["device"]["identifiers"], ["anchor"])

    def test_probe_has_bounded_projection(self):
        result = subprocess.run(
            [sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=5, check=True
        )
        self.assertEqual(
            set(json.loads(result.stdout)), {"connected", "wifi_signal", "temperature", "uptime"}
        )

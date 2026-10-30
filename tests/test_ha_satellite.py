import json
import subprocess
import sys
import unittest
from okabebot.ha_satellite import PROBE, discovery


class SatelliteTests(unittest.TestCase):
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

import unittest
from okabebot.ha_companion import command, discovery


class CompanionTests(unittest.TestCase):
    def test_bounded_commands(self):
        self.assertEqual(
            command("call", "PRESS", "desk"), ("/surfaces/move", {"location_id": "desk"})
        )
        self.assertEqual(command("volume", "25", "desk")[1], {"percent": 25})
        for name, value in [
            ("volume", "nan"),
            ("volume", "101"),
            ("volume", "1.5"),
            ("shell", "anything"),
            ("call", "other"),
        ]:
            with self.assertRaises(ValueError):
                command(name, value, "desk")

    def test_discovery_grouping(self):
        configs = list(discovery("lab/unit", "unit", "Companion", "Study"))
        self.assertEqual(len(configs), 9)
        for topic, config in configs:
            if config["unique_id"].endswith("_mac_screen"):
                self.assertEqual(config["device"]["identifiers"], ["unit_mac"])
                self.assertEqual(config["availability_mode"], "all")
                self.assertEqual(config["expire_after"], 75)
                continue
            self.assertEqual(config["device"]["suggested_area"], "Study")
            self.assertEqual(config["device"]["identifiers"], ["unit"])
            self.assertEqual(config["availability_topic"], "lab/unit/availability")

import unittest
from okabebot.ble_follow import AnchorGate


class AnchorTests(unittest.TestCase):
    def samples(self, gate, location, value, now):
        for offset in (2, 1, 0):
            gate.update(location, value, now - offset)

    def test_dwell_cooldown_and_return(self):
        g = AnchorGate(["down", "up"])
        self.samples(g, "up", -78, 10)
        self.assertIsNone(g.choose(10, "down"))
        self.samples(g, "up", -77, 17)
        self.assertEqual(g.choose(17, "down"), "up")
        self.samples(g, "down", -70, 50)
        self.assertIsNone(g.choose(50, "up"))
        self.samples(g, "down", -70, 140)
        self.assertIsNone(g.choose(140, "up"))
        self.samples(g, "down", -70, 147)
        self.assertEqual(g.choose(147, "up"), "down")

    def test_ambiguous_stale_blocked_or_other_location(self):
        for blocked, current, competing in (
            (True, "down", False),
            (False, "phone", False),
            (False, "down", True),
        ):
            g = AnchorGate(["down", "up"])
            self.samples(g, "up", -78, 10)
            if competing:
                g.update("down", -80, 10)
            g.choose(10, current, blocked)
            self.assertIsNone(g.choose(17, current, blocked))
        self.assertIsNone(g.choose(100, "down"))

    def test_no_move_from_single_packet(self):
        g = AnchorGate(["down", "up"])
        g.update("up", -60, 10)
        self.assertIsNone(g.choose(20, "down"))

    def test_invalid_thresholds_and_unbounded_sample_growth_rejected(self):
        for settings in ({"margin": float("nan")}, {"cooldown": 0}, {"window": 0}):
            with self.assertRaises(ValueError):
                AnchorGate(["down", "up"], **settings)
        g = AnchorGate(["down", "up"])
        for i in range(1000):
            g.update("down", -70, 10)
        self.assertLessEqual(len(g.samples["down"]), 256)

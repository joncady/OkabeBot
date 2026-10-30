import unittest
from okabebot.home_presence import HomeGate


class HomeTests(unittest.TestCase):
    def beat(self, g, now):
        for anchor in ("a", "b"):
            g.observe(anchor, {"state": "heartbeat"}, now)

    def test_absence_requires_healthy_scanners_and_departure_evidence(self):
        g = HomeGate(["a", "b"])
        g.intent = 0
        for now in range(0, 301, 5):
            self.beat(g, now)
            value = g.estimate(now)
        self.assertEqual(value, "probably_away")
        self.assertEqual(g.estimate(320), "unknown")
        h = HomeGate(["a", "b"])
        for now in range(0, 601, 5):
            self.beat(h, now)
            value = h.estimate(now)
        self.assertEqual(value, "unknown")

    def test_repeat_detection_confirms_home_and_dead_radio_never_away(self):
        g = HomeGate(["a", "b"])
        g.intent = 0
        self.beat(g, 100)
        for now in (100, 101, 102):
            g.observe("a", {"rssi": -80, "state": "sample"}, now)
        self.assertEqual(g.estimate(102), "home")
        self.assertEqual(g.estimate(600), "unknown")

    def test_old_door_does_not_turn_watch_charging_into_departure(self):
        g = HomeGate(["a", "b"])
        g.door = 0
        for now in (200, 201, 202):
            g.observe("a", {"rssi": -80, "state": "sample"}, now)
        for now in range(202, 803, 5):
            self.beat(g, now)
            value = g.estimate(now)
        self.assertEqual(value, "unknown")

    def test_return_requires_armed_absence_recent_door_and_is_consumed_once(self):
        from okabebot.home_presence import return_ready

        saved = {"away_since": 1000, "welcomed": False}
        self.assertTrue(return_ready("home", saved, 490, 500, 2000))
        self.assertFalse(return_ready("unknown", saved, 490, 500, 2000))
        self.assertFalse(return_ready("home", saved, None, 500, 2000))
        self.assertFalse(return_ready("home", saved, 100, 500, 2000))
        saved["welcomed"] = True
        self.assertFalse(return_ready("home", saved, 490, 500, 2000))

    def test_radio_unavailable_is_immediately_unknown(self):
        g = HomeGate(["a", "b"])
        g.intent = 0
        self.beat(g, 100)
        for now in (100, 101, 102):
            g.observe("a", {"rssi": -80, "state": "sample"}, now)
        g.observe("b", {"state": "unavailable"}, 102)
        self.assertEqual(g.estimate(102), "unknown")

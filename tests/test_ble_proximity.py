import unittest
import uuid

from pi.ble_proximity import Gate, beacon


class ProximityTests(unittest.TestCase):
    def test_beacon_matches_payload_not_a_rotating_mac_address(self):
        identity = uuid.UUID("00000000-0000-0000-0000-000000000001")
        raw = b"\x02\x15" + identity.bytes + b"\x00\x01\x00\x02\xc5"
        self.assertEqual(beacon(raw), (str(identity), 1, 2))
        self.assertIsNone(beacon(raw[:-1]))
        self.assertIsNone(beacon(b"not an ibeacon"))

    def test_dwell_median_and_cooldown_prevent_single_spikes_and_bouncing(self):
        g = Gate()
        self.assertIsNone(g.update(0, -40))
        for t in range(1, 6):
            self.assertIsNone(g.update(t, -85))
        events = [g.update(t, -50) for t in range(6, 17)]
        self.assertEqual(events.count("near"), 1)
        self.assertIsNone(g.update(18, -50))
        for t in range(19, 26):
            g.update(t, -90)
        self.assertNotIn("near", [g.update(t, -50) for t in range(26, 38)])

    def test_missing_samples_mean_unknown_and_never_an_away_action(self):
        g = Gate()
        self.assertEqual([g.update(t, -50) for t in range(5)].count("near"), 1)
        self.assertIsNone(g.update(30))
        self.assertEqual(g.state, "unknown")
        self.assertIsNone(g.update(31, -50))

    def test_invalid_thresholds_and_measurements_are_rejected(self):
        with self.assertRaises(ValueError):
            Gate(enter=-80, exit=-60)
        g = Gate()
        self.assertIsNone(g.update(0, float("nan")))
        self.assertIsNone(g.update(1, True))

    def test_stationary_phone_can_finish_dwell_without_inventing_samples(self):
        g = Gate()
        for t in [0, 1, 2]:
            self.assertIsNone(g.update(t, -50))
        self.assertEqual(g.update(4), "near")
        self.assertIsNone(g.update(5))
        g = Gate()
        g.update(0, -50)
        self.assertIsNone(g.update(4))

"""Invented registry keys; no participant data or device actions."""

import unittest
from okabebot.feed_choices import hints


class ChoiceTests(unittest.TestCase):
    def choice(self, key, unit, **fields):
        return hints(
            "sensor.invented",
            {"unique_id": key, **fields},
            {"attributes": {"unit_of_measurement": unit}},
            {},
        )

    def test_health_connect_provenance_without_claiming_samsung_origin(self):
        item = self.choice("invented_health_connect_daily_steps", "steps")
        self.assertIn("health.daily_steps", item["feed_fields"])
        self.assertIn("upstream app not verified", item["health_source"])
        self.assertNotIn("unique_id", item)
        self.assertEqual(self.choice("invented_health_connect_steps", "steps")["feed_fields"], [])
        self.assertEqual(
            self.choice("invented_health_connect_sleep_deep_duration", "min")["feed_fields"], []
        )
        self.assertEqual(self.choice("invented_steps_sensor", "steps")["feed_fields"], [])
        self.assertEqual(self.choice("invented_sleep_confidence", "%")["feed_fields"], [])
        self.assertIn(
            "health.sleep_minutes",
            self.choice("invented_health_connect_sleep_duration", "min")["feed_fields"],
        )
        self.assertNotIn(
            "health.sleep_minutes", self.choice("invented_sleep_duration", "ms")["feed_fields"]
        )

    def test_each_field_uses_compatible_semantics_not_just_domain(self):
        item = hints(
            "binary_sensor.example", {"unique_id": "fiction_is_charging"}, {"attributes": {}}, {}
        )
        self.assertEqual(item["feed_fields"], ["device_activity.charging"])
        item = hints("binary_sensor.example", {}, {"attributes": {"device_class": "occupancy"}}, {})
        self.assertEqual(item["feed_fields"], ["health.others"])
        item = self.choice("fiction_outdoor_temperature", "°F")
        self.assertIn("home_devices.sensors", item["feed_fields"])
        self.assertFalse(any(f.startswith("health.") for f in item["feed_fields"]))
        item = self.choice("fiction_cycle", "", platform="lg_thinq")
        self.assertIn("appliances.entities", item["feed_fields"])

    def test_guest_room_names_do_not_imply_other_person_detection(self):
        item = hints("binary_sensor.guest_bedroom_overheated", {}, {"attributes": {}}, {})
        self.assertNotIn("health.others", item["feed_fields"])

    def test_direct_watch_totals_are_distinct_from_health_connect(self):
        item = hints(
            "sensor.fiction_daily_steps",
            {"platform": "mobile_app"},
            {"attributes": {"unit_of_measurement": "steps"}},
            {"model": "Imaginary Watch"},
        )
        self.assertEqual(item["health_source"], "Watch app · direct sensor")
        self.assertIn("health.daily_steps", item["feed_fields"])

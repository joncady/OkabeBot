"""Synthetic browser context; never assumes user's room from character position."""

import unittest
import threading
from unittest.mock import Mock
from okabebot.chat_location import ground, resolve


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.place = {"id": "desk", "name": "Desk", "approved": True}
        self.surfaces = Mock()
        self.surfaces.snapshot.return_value = {"locations": [self.place]}
        self.surfaces.registered.return_value = self.place

    def test_paired_browser_defaults_here_and_explicit_selection_wins(self):
        self.assertEqual(resolve(self.surfaces, {"surface_secret": "opaque"}), self.place)
        self.assertEqual(resolve(self.surfaces, {"location_id": "desk"}), self.place)
        self.assertEqual(ground("Come here", self.place), "Come desk")
        self.assertEqual(ground("Move to TV", self.place), "Move to TV")

    def test_unknown_location_never_uses_current_character_as_fallback(self):
        self.assertIsNone(resolve(self.surfaces, {}))
        with self.assertRaises(ValueError):
            ground("Come here", None)
        with self.assertRaises(ValueError):
            resolve(self.surfaces, {"location_id": "invented"})
        self.surfaces.registered.side_effect = PermissionError()
        self.assertIsNone(resolve(self.surfaces, {"surface_secret": "unapproved"}))

    def test_saved_but_unregistered_surface_is_unpaired_not_an_exception(self):
        self.surfaces.registered.return_value = None
        self.assertIsNone(resolve(self.surfaces, {"surface_secret": "stale-browser"}))
        self.assertEqual(
            ground("What happened around the house today?", None),
            "What happened around the house today?",
        )
        with self.assertRaises(ValueError):
            ground("Come here", None)
        self.assertEqual(
            resolve(self.surfaces, {"surface_secret": "stale-browser", "location_id": "desk"}),
            self.place,
        )

    def test_browser_chat_application_accepts_stale_pairing_for_normal_chat(self):
        from types import SimpleNamespace
        from okabebot.application import Application

        app = Application.__new__(Application)
        self.surfaces.registered.return_value = None
        app.controller = SimpleNamespace(
            surfaces=self.surfaces,
            codex=SimpleNamespace(compose_preference=Mock(), text_turn=Mock(), specs={}),
        )
        app.text_conversation = Mock()
        app.text_conversation.lock = threading.RLock()
        app.text_conversation.send.return_value = {"reply": "A grounded reply.", "tools": []}
        result = app.execute("/amadeus/text", {"surface_secret": "stale", "text": "Hello"})
        self.assertEqual(result["reply"], "A grounded reply.")
        self.assertIsNone(result["location"])
        location = app.execute("/amadeus/text/location", {"surface_secret": "stale"})
        self.assertIsNone(location["location"])
        self.assertEqual(location["locations"], [{"id": "desk", "name": "Desk"}])

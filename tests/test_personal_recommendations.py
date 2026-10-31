"""Synthetic recommendation context: consent, privacy and no inferred inventory."""

from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from okabebot.amadeus import Store
from okabebot.amadeus_onboarding import SYSTEM, KEY
from okabebot.personal_recommendations import recommendation_context


class PersonalContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        with closing(Store(self.folder)) as store:
            store.remember(SYSTEM, KEY, {"profile": "synthetic", "paused": False, "guest": False})
            store.remember("synthetic", "conversation.preferences", {"enabled": True})
            store.remember(
                "synthetic",
                "context.preferences",
                {
                    "hobbies": ["paper folding"],
                    "food_drink": ["savory soup"],
                    "health": ["not returned"],
                },
            )

    def test_explicit_selected_context_only_no_inventory_or_health_claim(self):
        result = recommendation_context(self.folder, "food")
        self.assertEqual(result["preferences"], {"food_drink": ["savory soup"]})
        self.assertNotIn("not returned", str(result))
        self.assertIn("inventory", str(result["missing"]))

    def test_guest_pause_revoked_consent_and_others_block_context(self):
        for patch_value in ({"guest": True}, {"paused": True}):
            with closing(Store(self.folder)) as store:
                store.remember(
                    SYSTEM,
                    KEY,
                    {"profile": "synthetic", "paused": False, "guest": False, **patch_value},
                )
            self.assertFalse(recommendation_context(self.folder)["preferences"])
        with closing(Store(self.folder)) as store:
            store.remember(SYSTEM, KEY, {"profile": "synthetic", "paused": False, "guest": False})
        with patch("okabebot.amadeus_health.others_detected", return_value=True):
            self.assertEqual(recommendation_context(self.folder)["state"], "privacy_blocked")
        with closing(Store(self.folder)) as store:
            store.remember("synthetic", "conversation.preferences", {"enabled": False})
        self.assertFalse(recommendation_context(self.folder)["preferences"])

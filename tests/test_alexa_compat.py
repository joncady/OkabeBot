"""Version-specific adapter patch is idempotent and refuses unknown source."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "alexa_time_patch", Path(__file__).parents[1] / "scripts/patch-alexa-event-time.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AlexaCompatibilityTests(unittest.TestCase):
    def test_minimal_patch_keeps_ha_event_semantics_and_is_idempotent(self):
        source = """class AlexaVoiceEvent(object):
    def update(self, vocal_record):
        self._trigger_event(
            "triggered",
            {
                "intent": vocal_record.intent,
            },
        )
"""
        updated = module.patch_source(source)
        self.assertIn('"source_timestamp_ms": vocal_record.timestamp', updated)
        self.assertEqual(module.patch_source(updated), updated)
        self.assertIn("self._trigger_event(", updated)
        with self.assertRaises(ValueError):
            module.patch_source("class Unsupported: pass")

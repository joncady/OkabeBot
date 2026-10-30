import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "ring_patch", Path(__file__).parents[1] / "scripts/patch-ha-ring-push.py"
)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class RingPushPatchTests(unittest.TestCase):
    def test_header_order_and_padding(self):
        self.assertEqual("YWJjZA==", patch.webpush_parameter("p256ecdsa=unused; dh=YWJjZA", "dh"))
        self.assertEqual("YWJjZA==", patch.webpush_parameter("salt=YWJjZA==;rs=4096", "salt"))
        with self.assertRaises(ValueError):
            patch.webpush_parameter("p256ecdsa=unused", "dh")

    def test_patch_is_fail_closed_and_idempotent(self):
        source = """class FcmPushClient:
    def decode(self, msg):
        crypto_key = self._app_data_by_key(msg, "crypto-key")[3:]  # strip dh=
        salt = self._app_data_by_key(msg, "encryption")[5:]  # strip salt=
        if msg:
            self._handle_data_message(msg)
"""
        fixed = patch.patch_source(source)
        self.assertEqual(fixed, patch.patch_source(fixed))
        with self.assertRaises(ValueError):
            patch.patch_source("class Other: pass")
        namespace = {}
        exec(fixed, namespace)
        client = namespace["FcmPushClient"]()
        client._app_data_by_key = lambda *args: "dh=YWJjZA;salt=AA"
        # Exercise the packet exception boundary with synthetic bad payloads.
        client._app_data_by_key = lambda msg, key: "dh=YWJjZA" if key == "crypto-key" else "salt=AA"
        client._handle_data_message = lambda msg: (_ for _ in ()).throw(ValueError("bad key"))
        warnings = []
        client._log_warn_with_limit = warnings.append
        client.decode(True)
        self.assertEqual(1, len(warnings))

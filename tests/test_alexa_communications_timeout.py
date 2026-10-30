import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location(
    "communications_patch", Path("scripts/patch-alexa-communications-timeout.py")
)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

SOURCE = """import asyncio
class API:
    async def fetch(self):
        communications = (
            await self._communication_handler.get_communication_preferences(
                list(self._device_handler.devices.values())
            )
        )
        return communications
"""


class CommunicationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_timeout_preserves_cache_and_auth_failures_propagate(self):
        code = patch.patch_source(SOURCE)
        self.assertEqual(patch.patch_source(code), code)
        scope = {}
        exec(code.replace("asyncio.timeout(10)", "asyncio.timeout(0.01)"), scope)
        api = scope["API"]()
        api._device_handler = SimpleNamespace(devices={})

        async def slow(devices):
            await asyncio.sleep(1)

        handler = SimpleNamespace(
            get_communication_preferences=slow, _communication_preferences={"existing": "cached"}
        )
        api._communication_handler = handler
        self.assertEqual(await api.fetch(), {"existing": "cached"})

        async def auth_error(devices):
            raise PermissionError("authentication needed")

        handler.get_communication_preferences = auth_error
        with self.assertRaises(PermissionError):
            await api.fetch()

        async def fast(devices):
            return {"fresh": "value"}

        handler.get_communication_preferences = fast
        self.assertEqual(await api.fetch(), {"fresh": "value"})

    def test_unsupported_source_rejected(self):
        with self.assertRaises(ValueError):
            patch.patch_source("import asyncio\n")

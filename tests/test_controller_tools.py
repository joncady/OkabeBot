import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from okabebot.controller_tools import request, projection


class ControllerToolsTests(unittest.TestCase):
    def test_local_authenticated_request_uses_existing_controller(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "ptt").mkdir()
            Path(folder, "ptt/control.json").write_text(
                json.dumps({"url": "http://192.0.2.1:8768/#private"})
            )
            with (
                patch("okabebot.controller_tools.state_dir", return_value=Path(folder)),
                patch(
                    "okabebot.controller_tools.urlopen", return_value=io.BytesIO(b'{"active":true}')
                ) as opened,
            ):
                self.assertTrue(request("/focus/start", {"minutes": 25})["active"])
                req = opened.call_args.args[0]
                self.assertEqual(req.full_url, "http://192.0.2.1:8768/focus/start")
                self.assertEqual(req.get_header("X-hardware-token"), "private")
                self.assertEqual(json.loads(req.data), {"minutes": 25})

    def test_projection_excludes_unrelated_private_state(self):
        with patch(
            "okabebot.controller_tools.request", return_value={"tv": {}, "messages": ["private"]}
        ):
            self.assertEqual(projection("tv"), {"tv": {}})

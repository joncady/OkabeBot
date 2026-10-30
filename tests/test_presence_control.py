import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from okabebot import presence_control as p
from okabebot.presence_follow_service import Following


class ControlTests(unittest.TestCase):
    def test_stale_context_is_unknown_and_manual_move_holds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "home-presence"
            p.write(root / "config.json", {"anchors": [{"id": "a"}, {"id": "b"}]})
            p.write(
                root / "runtime.json",
                {"updated_at": 100, "presence": "home", "healthy_scanners": 2},
            )
            self.assertEqual(p.status(folder, 200)["presence"], "unknown")
            p.configure(folder, {"enabled": True})
            p.manual_move(folder)
            self.assertTrue(p.status(folder)["follow_enabled"])
            self.assertGreater(p.status(folder)["manual_hold_until"], 0)
            with self.assertRaises(ValueError):
                p.configure(folder, {"enabled": "true"})

    def test_disabled_or_failed_scanner_never_requests_a_move(self):
        with tempfile.TemporaryDirectory() as folder:
            p.write(
                Path(folder) / "home-presence/config.json", {"anchors": [{"id": "a"}, {"id": "b"}]}
            )
            worker = Following(folder, {"anchors": [{"id": "a"}, {"id": "b"}]})
            worker.request = Mock(side_effect=AssertionError("Must not call controller"))
            self.assertEqual(worker.step(100, 2), "disabled")
            p.configure(folder, {"enabled": True})
            self.assertEqual(worker.step(110, 1), "scanner unavailable")
            worker.request.assert_not_called()

    def test_controller_rejects_occupied_tv_and_unapproved_pair(self):
        from okabebot.application import Application
        from types import ModuleType
        import sys

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "home-presence"
            p.write(root / "config.json", {"anchors": [{"id": "a"}, {"id": "b"}]})
            p.write(
                root / "runtime.json",
                {
                    "updated_at": __import__("time").time(),
                    "presence": "home",
                    "healthy_scanners": 2,
                },
            )
            p.configure(folder, {"enabled": True})
            controller = Mock()
            controller.snapshot.return_value = {
                "busy": False,
                "recording": False,
                "focus": {},
                "music": {},
                "tv": {},
                "surfaces": {
                    "current_location": "a",
                    "phase": "pi",
                    "locations": [
                        {"id": "a", "adapter": "pi", "approved": True},
                        {"id": "b", "adapter": "cast", "approved": True},
                    ],
                },
            }
            controller.surfaces.cast_for.return_value.status.app_id = "occupied-fixture"
            module = ModuleType("pychromecast.config")
            module.APP_BACKDROP = "idle-fixture"
            with (
                patch("okabebot.application.state_dir", return_value=Path(folder)),
                patch.dict(sys.modules, {"pychromecast.config": module}),
            ):
                with self.assertRaises(ValueError):
                    Application(controller).execute("/presence/move", {"location_id": "b"})
                with self.assertRaises(ValueError):
                    Application(controller).execute("/presence/move", {"location_id": "other"})
            controller.surfaces.move.assert_not_called()

    def test_unexpected_location_change_creates_manual_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "home-presence"
            p.write(root / "config.json", {"anchors": [{"id": "a"}, {"id": "b"}]})
            p.configure(folder, {"enabled": True})
            worker = Following(folder, {"anchors": [{"id": "a"}, {"id": "b"}]})
            worker.expected = "a"
            worker.request = Mock(
                return_value={"surfaces": {"current_location": "b", "phase": "tv"}}
            )
            self.assertEqual(worker.step(100, 2), "manual hold")
            self.assertGreater(p.status(folder)["manual_hold_until"], 0)
            self.assertEqual(worker.request.call_count, 1)

    def test_recent_request_survives_restart_without_replaying(self):
        import time

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "home-presence"
            p.write(root / "config.json", {"anchors": [{"id": "a"}, {"id": "b"}]})
            p.configure(folder, {"enabled": True})
            p.write(root / "follow-request.json", {"at": time.time(), "target": "b"})
            worker = Following(folder, {"anchors": [{"id": "a"}, {"id": "b"}]})
            worker.request = Mock(side_effect=AssertionError("No replay"))
            self.assertEqual(worker.step(100, 2), "cooldown")
            worker.request.assert_not_called()

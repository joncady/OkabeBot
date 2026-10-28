"""Direct transfers never render an intermediate visit to the Pi."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from okabebot.surfaces import Surfaces


class DirectTransferTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patched = patch(
            "okabebot.surface_registry.registry_path",
            return_value=Path(folder.name) / "screens.json",
        )
        patched.start()
        self.addCleanup(patched.stop)
        self.s = Surfaces(Mock(), start=False)
        self.keys = ["a" * 64, "b" * 64]
        self.ids = []
        for key, name in zip(self.keys, ["Phone", "Mac"]):
            item = self.s.registry.register(key, name, "browser")
            self.s.registry.update(item["id"], {"approved": True}, self.s.settings["locations"])
            self.ids.append(item["id"])
        self.s.active_id, self.s.token, self.s.phase = self.ids[0], "source-token", "tv"
        self.s.ready = True
        self.s.last_seen = time.monotonic()

    def begin(self):
        result = self.s.move(self.ids[1], "http://controller")
        self.assertTrue(result["accepted"])
        return self.s.direct

    def test_ready_departed_entered_sequence_keeps_pi_away(self):
        transfer = self.begin()
        self.assertEqual(self.s.view(self.keys[0], {})["phase"], "tv")
        self.assertEqual(self.s.view(self.keys[1], {})["phase"], "preparing")
        self.s.tick()
        self.assertEqual(transfer.stage, "preparing")
        self.s.heartbeat(self.keys[1])
        self.s.tick()
        self.assertEqual(self.s.view(self.keys[0], {})["phase"], "leaving_tv")
        self.assertEqual(self.s.view(self.keys[1], {})["phase"], "preparing")
        self.s.acknowledge(self.keys[0], "departed", transfer.identifier)
        self.assertEqual(self.s.view(self.keys[0], {})["phase"], "idle")
        self.assertEqual(self.s.view(self.keys[1], {})["phase"], "entering_tv")
        self.s.acknowledge(self.keys[1], "entered", transfer.identifier)
        self.assertEqual(self.s.snapshot()["current_location"], self.ids[1])
        self.assertIsNone(self.s.direct)
        self.assertTrue(all(c.args[0]["phase"] == "away" for c in self.s.rpc.call_args_list))

    def test_target_failure_before_departure_preserves_source(self):
        transfer = self.begin()
        transfer.target_error = "Disconnected"
        self.s.tick()
        self.assertEqual(self.s.phase, "tv")
        self.assertEqual(self.s.active_id, self.ids[0])
        self.assertIsNone(self.s.direct)

    def test_failed_destination_after_departure_recovers_with_lease(self):
        transfer = self.begin()
        self.s.heartbeat(self.keys[1])
        self.s.tick()
        self.s.acknowledge(self.keys[0], "departed", transfer.identifier)
        self.s.receiver_closed(self.keys[1], transfer.identifier)
        self.s.tick()
        self.assertEqual(self.s.phase, "recovering")
        self.assertFalse(any(c.args[0]["phase"] == "arriving" for c in self.s.rpc.call_args_list))

    def test_closed_source_can_commit_only_once_destination_ready(self):
        transfer = self.begin()
        self.s.receiver_closed(self.keys[0], transfer.identifier)
        self.s.tick()
        self.assertEqual(transfer.stage, "preparing")
        self.s.heartbeat(self.keys[1])
        self.s.tick()
        self.assertEqual(transfer.stage, "entering")

    def test_unrelated_and_stale_acknowledgements_rejected(self):
        transfer = self.begin()
        for key, identifier in [(self.keys[0], "old"), ("c" * 64, transfer.identifier)]:
            with self.assertRaises(PermissionError):
                self.s.acknowledge(key, "departed", identifier)
        self.assertEqual(transfer.stage, "preparing")

    def test_direction_uses_source_target_positions_and_return_recomputes(self):
        places = self.s.settings["locations"]
        self.s.registry.update(self.ids[0], {"position": [2, 0]}, places)
        self.s.registry.update(self.ids[1], {"position": [-2, 0]}, places)
        transfer = self.begin()
        self.assertEqual(transfer.direction, "left")
        self.assertEqual(self.s.view(self.keys[0], {})["tv_side"], "right")
        self.s.return_home()
        self.assertEqual(self.s.phase, "leaving_tv")
        self.assertEqual(self.s.travel_direction, "right")

    def test_revoked_destination_cancels_before_source_departure(self):
        self.begin()
        self.s.layout({"id": self.ids[1], "approved": False})
        self.assertIsNone(self.s.direct)
        self.assertEqual(self.s.phase, "tv")
        self.assertEqual(self.s.active_id, self.ids[0])

    def test_stale_launch_cannot_claim_new_receiver(self):
        from types import SimpleNamespace
        from pychromecast.config import APP_DASHCAST

        cast = Mock(status=SimpleNamespace(app_id=APP_DASHCAST, session_id="stale"))
        self.s.cast_getter = lambda: cast
        self.s.receiver_session = "current"
        with patch("pychromecast.controllers.BaseController.launch"):
            self.s._launch("http://test/tv/#expired-token")
        self.assertEqual(self.s.receiver_session, "current")
        cast.quit_app.assert_not_called()

    def test_reply_route_resolves_to_actual_destination_after_direct_handoff(self):
        from types import SimpleNamespace
        from okabebot.application import Application
        import threading

        transfer = self.begin()
        controller = SimpleNamespace(surfaces=self.s, surface_audio=Mock())
        controller.surface_audio.ready.return_value = True
        app = Application(controller)
        self.s.heartbeat(self.keys[1])
        self.s.tick()  # Source is departing; there is deliberately no stable owner.
        result = []
        with patch("okabebot.audio_output.target", return_value="pi"):
            thread = threading.Thread(
                target=lambda: result.append(app.execute("/audio/resolve", {"purpose": "reply"}))
            )
            thread.start()
            self.s.acknowledge(self.keys[0], "departed", transfer.identifier)
            self.s.acknowledge(self.keys[1], "entered", transfer.identifier)
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [{"target": "browser", "device_id": self.ids[1], "ready": True}])

"""Restart receipts use synthetic sessions and never connect to a real receiver."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from pychromecast.config import APP_DASHCAST
from okabebot.surface_ownership import Ownership
from okabebot.surfaces import Surfaces


class OwnershipTests(unittest.TestCase):
    def test_atomic_private_receipt_and_exact_retirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ownership.json"
            journal = Ownership(path)
            journal.remember("tv", "synthetic-session")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            journal.forget("tv", "another-session")
            self.assertTrue(Ownership(path).sessions)
            journal.forget("tv", "synthetic-session")
            self.assertEqual({}, Ownership(path).sessions)

    def make(self, path, cast):
        s = Surfaces(
            Mock(return_value={}), cast_getter=lambda: cast, start=False, ownership_path=path
        )
        return s

    def test_restart_retires_exact_owned_receiver_then_waits_for_pi_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ownership.json"
            s = self.make(path, None)
            s.ownership.remember(s.active_id, "ours")
            cast = Mock(status=SimpleNamespace(app_id=APP_DASHCAST, session_id="ours"))
            restarted = self.make(path, cast)
            self.assertEqual("reconciling", restarted.phase)
            self.assertIsNone(restarted.snapshot()["current_location"])
            with self.assertRaises(ValueError):
                restarted.return_home()
            restarted.tick(100)
            cast.quit_app.assert_called_once()
            self.assertEqual("away", restarted.rpc.call_args.args[0]["phase"])
            self.assertEqual("reconciling", restarted.phase)
            cast.status.app_id, cast.status.session_id = "backdrop", "new"
            restarted.tick(103)
            self.assertEqual("entering_pi", restarted.phase)
            self.assertFalse(Ownership(path).sessions)
            restarted.tick(104)
            self.assertEqual("arriving", restarted.rpc.call_args.args[0]["phase"])
            restarted.rpc.return_value = {
                "presence": {"transition_id": restarted.identifier, "rendered": "home"}
            }
            restarted.tick(105)
            self.assertEqual("pi", restarted.phase)

    def test_other_sessions_never_stopped_and_unreachable_keeps_unknown(self):
        for app, session in [(APP_DASHCAST, "not-ours"), ("youtube", "ours"), (None, None)]:
            with self.subTest(app=app), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "ownership.json"
                original = self.make(path, None)
                original.ownership.remember(original.active_id, "ours")
                unavailable = self.make(path, None)
                unavailable.tick(100)
                unavailable.tick(1000)
                self.assertEqual("reconciling", unavailable.phase)
                cast = Mock(status=SimpleNamespace(app_id=app, session_id=session))
                unavailable.cast_getter = lambda: cast
                unavailable.tick(1004)
                cast.quit_app.assert_not_called()
                self.assertEqual("entering_pi", unavailable.phase)

    def test_corrupt_receipt_is_explicit_fault_without_stopping_unknown_receiver(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ownership.json"
            path.write_text("{corrupt")
            cast = Mock(status=SimpleNamespace(app_id=APP_DASHCAST, session_id="unknown"))
            s = self.make(path, cast)
            s.tick(100)
            self.assertEqual(s.phase, "reconciling")
            self.assertIn("unreadable", s.error)
            cast.quit_app.assert_not_called()
            self.assertEqual(path.read_text(), "{corrupt")

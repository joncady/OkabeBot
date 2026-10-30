"""Synthetic display events and fake handoffs; no host display or hardware changes."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from okabebot.mac_screen import MacScreen, DEFAULTS


class MacScreenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 2_000_000_000
        self.service = MacScreen(Path(self.tmp.name), clock=lambda: self.now)
        self.item = {"id": "screen-invented", "adapter": "mac", "approved": True}
        self.cfg = dict(DEFAULTS, enabled=True, destination=self.item["id"])
        self.service.configure(self.cfg, [self.item])
        self.state = {"surfaces": {"phase": "pi", "current_location": "invented-pi"}}
        self.move = Mock(return_value={"accepted": True})

    def signal(self, **overrides):
        data = dict(state="on", cause="wake", observed_at=self.now, event_id="invented-wake")
        data.update(overrides)
        return self.service.signal(self.item, data, lambda: self.state, self.move)

    def test_only_fresh_wake_moves_once_and_snapshot_does_not_replay(self):
        self.assertTrue(self.signal()["moved"])
        self.signal(cause="snapshot", event_id="heartbeat")
        self.assertFalse(self.signal()["accepted"])
        self.assertEqual(self.move.call_count, 1)
        self.assertEqual(self.service.snapshot()["state"], "on")
        self.now += 76
        self.assertEqual(self.service.snapshot()["state"], "unknown")
        with self.assertRaises(ValueError):
            self.signal(observed_at=self.now - 31)

    def test_busy_media_focus_moving_and_unapproved_are_blocked(self):
        for blocked in (
            {"busy": True},
            {"recording": True},
            {"focus": {"active": True}},
            {"music": {"is_playing": True}},
            {"tv": {"is_playing": True}},
            {"surfaces": {"phase": "preparing"}},
        ):
            self.now += 100
            self.state = {"surfaces": {"phase": "pi"}, **blocked}
            self.assertFalse(self.signal()["moved"])
        self.move.assert_not_called()
        with self.assertRaises(PermissionError):
            self.service.signal(dict(self.item, adapter="browser"), {}, lambda: {}, self.move)

    def test_uncertain_move_consumed_and_not_replayed(self):
        self.move.side_effect = RuntimeError("unavailable")
        self.assertFalse(self.signal()["moved"])
        self.move.side_effect = None
        self.assertFalse(self.signal()["accepted"])
        self.assertEqual(self.move.call_count, 1)

    def test_manual_hold_and_media_choice_are_editable(self):
        from okabebot.presence_control import write

        write(
            Path(self.tmp.name) / "home-presence/follow.json", {"manual_hold_until": self.now + 600}
        )
        self.assertEqual(self.signal()["reason"], "manual location hold")
        self.service.configure(
            dict(self.cfg, respect_manual_hold=False, respect_media=False), [self.item]
        )
        self.state["music"] = {"is_playing": True}
        self.now += 1
        self.assertTrue(self.signal()["moved"])

    def test_startup_and_sleep_do_not_move_or_restore_state_after_restart(self):
        self.signal(cause="snapshot")
        self.now += 1
        self.signal(cause="sleep", state="off")
        self.assertEqual(self.service.snapshot()["state"], "off")
        self.move.assert_not_called()
        self.assertEqual(
            MacScreen(Path(self.tmp.name), clock=lambda: self.now).snapshot()["state"], "unknown"
        )

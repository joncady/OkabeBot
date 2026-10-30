import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from okabebot.screen_power import DEFAULTS, ScreenPower, intervals, validate
from okabebot import runtime_policy
from pi.display_power import Power


class ScreenNightTests(unittest.TestCase):
    def test_overnight_timezone_and_disabled(self):
        now = datetime(2026, 11, 1, 7, tzinfo=timezone.utc).timestamp()
        cfg = {**DEFAULTS, "enabled": True, "timezone": "America/Los_Angeles"}
        spans = intervals(cfg, now)
        self.assertTrue(any(a <= now < b for a, b in spans))
        self.assertEqual(11 * 3600, spans[0][1] - spans[0][0])  # DST fall-back
        self.assertEqual([], intervals(DEFAULTS, now))
        with self.assertRaises(ValueError):
            validate({**cfg, "timezone": "not/a/zone"})

    def test_sleep_wake_override_and_restart_with_expired_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "power.json"
            path.write_text(
                json.dumps({"intervals": [[1, 2], [299999, 300100]], "wake_minutes": 1})
            )
            clock = Mock(return_value=300000)
            p = Power(":0", path, clock=clock)
            p.switch = Mock(return_value=True)
            self.assertFalse(p.tick()["awake"])
            self.assertTrue(p.wake()["awake"])
            clock.return_value += 61
            self.assertFalse(p.tick()["awake"])
            p.set_schedule({"intervals": [], "wake_minutes": 1})
            self.assertTrue(p.tick()["awake"])

    def test_rpc_policy_and_unavailable_device(self):
        with tempfile.TemporaryDirectory() as directory:
            rpc = Mock(return_value={"awake": True, "error": None})
            s = ScreenPower(directory, rpc, clock=lambda: 1000000)
            self.assertEqual("connected", s.configure(DEFAULTS)["state"])
            self.assertEqual([], rpc.call_args.args[0]["intervals"])
            rpc.side_effect = OSError("offline")
            s.next_check = 0
            s.tick()
            self.assertEqual("unavailable", s.snapshot()["state"])

    def test_dpms_fallback_disables_automatic_idle_timeouts(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Mock(return_value=Mock(returncode=0, stdout=""))
            p = Power(":0", Path(directory) / "power.json", run=run)
            self.assertTrue(p.switch(False))
            commands = [c.args[0] for c in run.call_args_list]
            self.assertIn(["xset", "-display", ":0", "dpms", "0", "0", "0"], commands)
            self.assertEqual("off", commands[-1][-1])

    def test_startup_settings_are_persistent_and_validated(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(runtime_policy, "docker_login") as docker,
        ):
            cfg = runtime_policy.configure(
                directory, {"docker_at_login": True, "prevent_sleep_on_ac": True}
            )
            self.assertEqual(cfg, runtime_policy.settings(directory))
            docker.assert_called_once_with(True)
            with self.assertRaises(ValueError):
                runtime_policy.configure(directory, {"prevent_sleep_on_ac": "yes"})

    def test_failed_hardware_commands_are_rate_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = Mock(return_value=1000)
            p = Power(":0", Path(directory) / "power.json", clock=clock)
            p.switch = Mock(return_value=False)
            for _ in range(10):
                self.assertIsNone(p.tick()["awake"])
            self.assertEqual(1, p.switch.call_count)
            clock.return_value += 31
            p.tick()
            self.assertEqual(2, p.switch.call_count)

import subprocess
import unittest
from unittest.mock import Mock, patch
from pi.display_power import keep_awake


class DisplayPowerTests(unittest.TestCase):
    def test_wakes_and_disables_sleep_on_the_established_display(self):
        with patch("pi.display_power.subprocess.run", return_value=Mock(returncode=0)) as run:
            self.assertTrue(keep_awake(":0.0"))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(["xset", "-display", ":0.0", "dpms", "force", "on"], commands[0])
        self.assertIn(["xset", "-display", ":0.0", "-dpms"], commands)
        self.assertIn(["xset", "-display", ":0.0", "s", "off"], commands)
        self.assertIn(["xset", "-display", ":0.0", "s", "noblank"], commands)

    def test_missing_or_unresponsive_xset_does_not_crash_startup(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("xset", 3)):
            with patch("pi.display_power.subprocess.run", side_effect=error):
                self.assertFalse(keep_awake(":0"))

    def test_unsupported_dpms_does_not_skip_screen_saver_settings(self):
        with patch(
            "pi.display_power.subprocess.run",
            side_effect=[
                Mock(returncode=1),
                Mock(returncode=1),
                Mock(returncode=0),
                Mock(returncode=0),
            ],
        ) as run:
            self.assertFalse(keep_awake(":0"))
            self.assertEqual("noblank", run.call_args.args[0][-1])

    def test_opt_out_does_not_modify_desktop_settings(self):
        with patch("pi.display_power.subprocess.run") as run:
            self.assertTrue(keep_awake(":0", enabled=False))
            run.assert_not_called()

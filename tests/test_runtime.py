from copy import deepcopy
import json
from pathlib import Path
import plistlib
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from okabebot import runtime
from okabebot.config import DEFAULTS
from okabebot.integration_auth import persistent_token


class RuntimeTests(unittest.TestCase):
    def test_external_speech_lock_prevents_health_restart_and_clears_on_release(self):
        import fcntl

        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(runtime.speech_active(folder))
            with (Path(folder) / "character-speech.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                self.assertTrue(runtime.speech_active(folder))
            self.assertFalse(
                runtime.speech_active(folder), "A stale lock file is not active speech"
            )

    def test_child_restart_backoff_and_owned_process_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            child = runtime.Child("worker", ["python", "worker.py"], folder, Path(folder))
            first = Mock(pid=123)
            first.poll.return_value = None
            with patch.object(runtime.subprocess, "Popen", return_value=first) as popen:
                child.start()
                child.start()
                self.assertEqual(popen.call_count, 1)
                self.assertIn("OKABEBOT_PARENT_PID", popen.call_args.kwargs["env"])
                first.poll.return_value = 1
                child.check()
                child.start()
                self.assertEqual(popen.call_count, 1)
                self.assertGreater(child.retry_at, time.monotonic())
                child.retry_at = 0
                first.poll.return_value = None
                child.start()
                self.assertEqual(popen.call_count, 2)
                with patch.object(runtime.os, "killpg") as kill:
                    child.stop()
                    kill.assert_called_once()
                    first.wait.assert_called()

    def test_launch_agent_has_safe_argv_and_explicit_working_directory(self):
        with tempfile.TemporaryDirectory(prefix="hardware lab ") as folder:
            root = Path(folder)
            config = root / "private.local.json"
            with (
                patch.object(runtime.Path, "home", return_value=root),
                patch.object(runtime, "state_dir", return_value=root / "state"),
                patch.object(runtime.subprocess, "run") as run,
                patch.object(runtime.sys, "platform", "darwin"),
            ):
                runtime.install(config)
            files = list((root / "Library/LaunchAgents").glob("*.plist"))
            value = plistlib.loads(files[0].read_bytes())
            self.assertEqual(value["ProgramArguments"][-1], str(config))
            self.assertEqual(value["WorkingDirectory"], str(root))
            self.assertTrue(value["RunAtLoad"])
            self.assertTrue(value["KeepAlive"])
            self.assertEqual(set(value["EnvironmentVariables"]), {"PATH"})
            self.assertEqual(run.call_args.args[0][1], "bootstrap")

    def test_controller_token_persists_and_stays_distinct_from_publisher(self):
        with tempfile.TemporaryDirectory() as folder:
            first = persistent_token(folder, "controller-token")
            self.assertEqual(first, persistent_token(folder, "controller-token"))
            self.assertNotEqual(first, persistent_token(folder, "notification-token"))
            self.assertEqual((Path(folder) / "controller-token").stat().st_mode & 0o777, 0o600)

    def test_bridge_initialization_does_not_require_online_hardware(self):
        from okabebot import bridge as module

        with tempfile.TemporaryDirectory() as folder:
            config = deepcopy(DEFAULTS)
            config["state_dir"] = folder
            config["spotify"]["source"] = "api"
            endpoint = Mock()
            endpoint.rpc.side_effect = OSError("offline")
            with (
                patch.object(module, "state_dir", return_value=Path(folder)),
                patch.object(module, "get_config", return_value=config),
                patch.object(module, "device", return_value=endpoint),
                patch.object(module, "create_media_source", return_value=Mock()),
                patch.object(module, "TeamResolver", return_value=Mock()),
                patch.dict("sys.modules", {"faster_whisper": Mock(WhisperModel=Mock())}),
                patch.object(module.Bridge, "show_activity"),
                patch.object(module.threading.Thread, "start"),
            ):
                bridge = module.Bridge(8768, transcribe_only=True)
                self.assertTrue((Path(folder) / "ptt/control.json").exists())
                self.assertFalse(bridge.device_health["voice"]["available"])
                self.assertTrue(bridge.enabled)
                bridge.close()

    def test_corrupt_or_unavailable_controller_status_is_not_healthy(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(runtime.controller_state(Path(folder)))
            root = Path(folder) / "ptt"
            root.mkdir()
            (root / "control.json").write_text(json.dumps({"url": "http://127.0.0.1:1/#token"}))
            self.assertIsNone(runtime.controller_state(Path(folder)))

    def test_login_service_retries_transient_unload_race(self):
        import subprocess

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (
                patch.object(runtime.Path, "home", return_value=root),
                patch.object(runtime, "state_dir", return_value=root / "state"),
                patch.object(runtime.sys, "platform", "darwin"),
                patch.object(runtime.time, "sleep") as sleep,
                patch.object(
                    runtime.subprocess,
                    "run",
                    side_effect=[Mock(), subprocess.CalledProcessError(5, "launchctl"), Mock()],
                ) as run,
            ):
                runtime.install(root / "config.json")
                self.assertEqual(run.call_count, 3)
                sleep.assert_called_once_with(1)

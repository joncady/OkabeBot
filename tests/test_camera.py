import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pi"))
from camera import Camera


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.camera = Camera(self.tmp.name)
        backend = patch.object(self.camera, "executable", return_value=("raspivid", "legacy"))
        backend.start()
        self.addCleanup(backend.stop)

    @patch("camera.subprocess.run")
    def test_invalid_duration_never_starts_camera(self, run):
        for seconds in (0, -1, 21, True, 2.5):
            with self.assertRaises(ValueError):
                self.camera.capture(video=True, duration_seconds=seconds)
        run.assert_not_called()

    @patch("camera.subprocess.run")
    def test_concurrent_capture_rejected(self, run):
        self.camera.lock.acquire()
        with self.assertRaisesRegex(ValueError, "busy"):
            self.camera.capture(video=True)
        run.assert_not_called()
        self.camera.lock.release()

    @patch("camera.subprocess.run")
    def test_failed_recording_releases_camera_and_removes_partial(self, run):
        import subprocess

        def fail(args, **kwargs):
            Path(args[args.index("-o") + 1]).write_bytes(b"partial")
            raise subprocess.TimeoutExpired(args, 15)

        run.side_effect = fail
        with self.assertRaises(RuntimeError):
            self.camera.capture(video=True)
        run.assert_called_once()
        self.assertFalse(self.camera.lock.locked())
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

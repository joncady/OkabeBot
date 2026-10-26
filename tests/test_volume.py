import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from pi.volume import Volume


class VolumeTests(unittest.TestCase):
    def mixer(self):
        level = [20]

        def run(command, **kwargs):
            if "sset" in command:
                level[0] = int(command[-1].removesuffix("%"))
            return SimpleNamespace(stdout="Front Left: Playback [" + str(level[0]) + "%] [on]")

        return run

    def test_volume_mute_and_restart_persistence(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("pi.volume.subprocess.run", side_effect=self.mixer()),
        ):
            path = Path(folder) / "volume.local.json"
            volume = Volume({}, path)
            self.assertEqual(volume.snapshot()["percent"], 20)
            self.assertEqual(volume.set(10)["percent"], 10)
            self.assertEqual(json.loads(path.read_text())["percent"], 10)
            self.assertEqual(Volume({}, path).snapshot()["percent"], 10)
            volume.set(0)
            self.assertEqual(Volume({}, path).snapshot()["percent"], 0)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_bad_input_never_invokes_mixer(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("pi.volume.subprocess.run", side_effect=self.mixer()) as mixer,
        ):
            volume = Volume({}, Path(folder) / "volume.local.json")
            before = mixer.call_count
            for value in (-1, 101, True, 10.5, "20"):
                with self.assertRaises(ValueError):
                    volume.set(value)
            self.assertEqual(mixer.call_count, before)

    def test_unavailable_mixer_does_not_prevent_voice_startup(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("pi.volume.subprocess.run", side_effect=FileNotFoundError()),
        ):
            volume = Volume({}, Path(folder) / "volume.local.json")
            self.assertFalse(volume.snapshot()["available"])
            with self.assertRaises(RuntimeError):
                volume.set(20)

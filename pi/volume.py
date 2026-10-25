"""ALSA speaker level with local restart persistence. Python 3.7 compatible."""

import json
from pathlib import Path
import re
import subprocess
import threading


class Volume:
    def __init__(self, config, path=None):
        self.path = Path(path or Path(__file__).parent / "volume.local.json")
        self.command = ["amixer"]
        if config.get("audio_mixer_card"):
            self.command += ["-c", str(config["audio_mixer_card"])]
        self.control = config.get("audio_mixer_control", "Master")
        self.lock = threading.Lock()
        self.state = {"available": False, "percent": None}
        try:
            if self.path.exists():
                self.set(json.loads(self.path.read_text())["percent"])
            else:
                self.get()
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
            self.state = {"available": False, "percent": None, "error": "Speaker mixer unavailable"}

    def snapshot(self):
        return dict(self.state)

    def _run(self, args):
        try:
            result = subprocess.run(
                self.command + args, capture_output=True, text=True, check=True, timeout=3
            )
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError("Speaker mixer unavailable") from None
        levels = re.findall(r"\[(\d+)%\]", result.stdout)
        if not levels:
            raise ValueError("Mixer did not report speaker level")
        percent = max(int(value) for value in levels)
        if not 0 <= percent <= 100:
            raise ValueError("Invalid mixer response")
        self.state = {"available": True, "percent": percent}
        return self.snapshot()

    def get(self):
        with self.lock:
            return self._run(["sget", self.control])

    def set(self, percent):
        if type(percent) is not int or not 0 <= percent <= 100:
            raise ValueError("Volume must be an integer from 0 to 100")
        with self.lock:
            result = self._run(["sset", self.control, str(percent) + "%"])
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"percent": result["percent"]}))
            temporary.chmod(0o600)
            temporary.replace(self.path)
            return result

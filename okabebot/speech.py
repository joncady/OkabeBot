"""Speech backends: macOS say or Linux eSpeak NG, normalized to 16 kHz WAV."""

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import get_config

PRESETS = ("warm", "calm", "robotic")
RATES = {"neutral": 175, "happy": 182, "curious": 168, "concerned": 155, "excited": 192}


def engine():
    name = get_config()["speech"]["engine"]
    return ("say" if platform.system() == "Darwin" else "espeak") if name == "auto" else name


def voices():
    key = "mac_voices" if engine() == "say" else "linux_voices"
    return get_config()["speech"][key]


def normalize(source, target):
    if platform.system() == "Darwin":
        args = ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(source), str(target)]
    else:
        args = [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    subprocess.run(args, check=True, capture_output=True, timeout=20)


def synthesize(text, emotion, voice, target):
    if not text.strip() or len(text) > 600 or emotion not in RATES or voice not in PRESETS:
        raise ValueError("Use 1–600 characters and a known emotion/voice")
    with tempfile.TemporaryDirectory() as tmp:
        source, audio = Path(tmp) / "text.txt", Path(tmp) / "speech.wav"
        source.write_text(text.replace("[[", "").replace("]]", ""))
        name = voices()[voice]
        if engine() == "say":
            audio = Path(tmp) / "speech.aiff"
            args = [
                "say",
                "-v",
                name,
                "-r",
                str(RATES[emotion]),
                "-f",
                str(source),
                "-o",
                str(audio),
            ]
        else:
            executable = shutil.which("espeak-ng") or shutil.which("espeak")
            if not executable:
                raise RuntimeError("Install espeak-ng and ffmpeg for Linux speech")
            args = [
                executable,
                "-v",
                name,
                "-s",
                str(RATES[emotion]),
                "-f",
                str(source),
                "-w",
                str(audio),
            ]
        subprocess.run(args, check=True, capture_output=True, timeout=30)
        normalize(audio, target)

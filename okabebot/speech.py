"""Speech backends: macOS say or Linux eSpeak NG, normalized to 16 kHz WAV."""

import os
import json
from urllib.request import Request, urlopen
import platform
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from .config import get_config, state_dir

PRESETS = ("warm", "calm", "robotic")
RATES = {"neutral": 175, "happy": 182, "curious": 168, "concerned": 155, "excited": 192}


def engine():
    name = get_config()["speech"]["engine"]
    try:
        name = json.loads((state_dir() / "speech-settings.json").read_text())["engine"]
    except (OSError, ValueError, KeyError):
        pass
    return ("say" if platform.system() == "Darwin" else "espeak") if name == "auto" else name


def voices():
    key = (
        "cloud_voices"
        if engine() == "openai"
        else ("mac_voices" if engine() == "say" else "linux_voices")
    )
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
        if engine() == "openai":
            count = 0
            with wave.open(str(audio), "wb") as wav:
                wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                for chunk in pcm_chunks(text, emotion, voice):
                    count += len(chunk)
                    if count > 30 * 48000 or len(chunk) % 2:
                        raise ValueError("Cloud audio exceeds 30 seconds or has invalid PCM")
                    wav.writeframes(chunk)
            if not count:
                raise RuntimeError("Speech provider returned no audio")
            normalize(audio, target)
            return
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


def pcm_chunks(text, emotion, voice):
    """Stream 24 kHz PCM; one HTTP request, no retries after audio begins."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY on the controller to use cloud speech")
    settings = get_config()["speech"]
    request = Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(
            {
                "model": settings["cloud_model"],
                "voice": settings["cloud_voices"][voice],
                "input": text,
                "response_format": "pcm",
                "instructions": "Speak naturally and concisely. Emotional delivery: " + emotion,
            }
        ).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        while True:
            chunk = response.read(24000)
            if not chunk:
                break
            yield chunk

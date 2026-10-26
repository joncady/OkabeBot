"""Speech backends: macOS say or Linux eSpeak NG, normalized to 16 kHz WAV."""

import os
import json
from urllib.request import Request, urlopen
import platform
import shutil
import subprocess
import tempfile
import wave
import socket
import struct
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
        if engine() in ("openai", "local"):
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
    if engine() == "local":
        yield from local_pcm_chunks(text, emotion, voice)
        return
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


def _receive(connection, length):
    data = bytearray()
    while len(data) < length:
        chunk = connection.recv(length - len(data))
        if not chunk:
            raise RuntimeError("Local speech worker disconnected before completion")
        data.extend(chunk)
    return bytes(data)


def local_pcm_chunks(text, emotion, voice):
    """Private Unix socket: JSON request, length-prefixed mono PCM16 at 24 kHz."""
    from .profiles import current_character

    request = {
        "text": text,
        "emotion": emotion,
        "voice": voice,
        "character": current_character()["style"],
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(30)
        connection.connect(get_config()["speech"]["local_socket"])
        connection.sendall(json.dumps(request).encode() + b"\n")
        total = 0
        while True:
            length = struct.unpack("!I", _receive(connection, 4))[0]
            if length == 0:
                return
            total += length
            if length % 2 or length > 48000 or total > 30 * 48000:
                raise RuntimeError("Invalid or excessive PCM from local speech worker")
            yield _receive(connection, length)


def local_worker_status():
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(get_config()["speech"]["local_socket"])
        connection.sendall(b'{"op":"status"}\n')
        size = struct.unpack("!I", _receive(connection, 4))[0]
        if not 0 < size <= 8192:
            raise ValueError("Invalid worker status")
        return json.loads(_receive(connection, size))


def health():
    backend = engine()
    if backend == "local":
        try:
            result = local_worker_status()
            from .profiles import current_character

            supported = current_character()["style"] in result.get("characters", [])
            return {
                "backend": backend,
                "available": bool(result.get("ready") and supported),
                "worker_ready": bool(result.get("ready")),
                "characters": result.get("characters", []),
                "error": None if supported else "Selected character has no voice reference",
            }
        except Exception:
            return {
                "backend": backend,
                "available": False,
                "error": "Local voice worker unavailable or warming",
            }
    available = (
        bool(os.getenv("OPENAI_API_KEY"))
        if backend == "openai"
        else bool(
            shutil.which("say")
            if backend == "say"
            else shutil.which("espeak-ng") or shutil.which("espeak")
        )
    )
    return {
        "backend": backend,
        "available": available,
        "error": None if available else "Speech backend is not configured",
    }

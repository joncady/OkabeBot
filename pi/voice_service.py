"""AIY Voice Pi: loopback-only audio and button service (Python 3.7)."""

import base64
import collections
import io
import json
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from buttons import board
from device_config import load
from ptt_recorder import PushToTalk
from stream_audio import StreamAudio
from music_meter import MusicMeter
from volume import Volume
from prepared_audio import PreparedAudio


def validate_wav(raw):
    if len(raw) > 1_000_000:
        raise ValueError("Audio exceeds size limit")
    with wave.open(io.BytesIO(raw)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 16000):
            raise ValueError("Expected mono 16-bit 16000 Hz WAV")
        duration = w.getnframes() / 16000
        if not 0 < duration <= 30:
            raise ValueError("Audio must be 0–30 seconds")
    return duration


class Voice:
    def __init__(self):
        self.audio_lock = threading.Lock()
        self.prepared = PreparedAudio(validate_wav)
        self.events_lock = threading.Lock()
        self.events = collections.deque(maxlen=100)
        self.sequence = 0
        self.session = uuid.uuid4().hex
        self.pressed = False
        self.config = load()
        self.volume = Volume(self.config)
        self.board = board(self.config)
        self.music_meter = MusicMeter(self.audio_lock, self.config["audio_device"])
        self.stream = StreamAudio(self.audio_lock, self.config["audio_device"])
        self.ptt = PushToTalk(self.audio_lock, self.board.led, self.config["audio_device"])
        self.board.button.when_pressed = lambda: self.event(True)
        self.board.button.when_released = lambda: self.event(False)

    def event(self, pressed):
        if pressed:
            self.music_meter.preempt()
        self.ptt.button(pressed)
        with self.events_lock:
            self.pressed = pressed
            self.sequence += 1
            self.events.append(
                {
                    "id": self.sequence,
                    "type": "pressed" if pressed else "released",
                    "timestamp": time.time(),
                }
            )

    def request(self, data):
        op = data.get("op")
        if op == "audio_prepare":
            prepared = self.prepared.prepare(base64.b64decode(data["wav_base64"], validate=True))
            prepared["server_time"] = time.time()
            return prepared
        if op == "play_prepared":
            raw = self.prepared.take(data.get("prepared_id"))
            data = {
                "op": "play",
                "wav_base64": base64.b64encode(raw).decode(),
                "start_at": data.get("start_at", time.time()),
            }
            op = "play"

        if op == "volume":
            return self.volume.set(data["percent"]) if "percent" in data else self.volume.get()
        if op == "music_meter":
            return self.music_meter.control(data.get("enabled", False))
        if op in ("record", "play", "stream_start"):
            self.music_meter.preempt()
        if op in ("stream_start", "stream_chunk", "stream_end", "stream_abort"):
            return self.stream.request(data)
        if op == "ptt":
            return self.ptt.control(data.get("enabled", False), data.get("acknowledge"))
        if op in ("status", "events"):
            after = data.get("after_id", 0)
            if type(after) is not int or after < 0:
                raise ValueError("after_id must be nonnegative")
            with self.events_lock:
                return {
                    "session_id": self.session,
                    "pressed": self.pressed,
                    "latest_id": self.sequence,
                    "events": [e for e in self.events if e["id"] > after],
                    "audio_busy": self.audio_lock.locked(),
                    "volume": self.volume.snapshot(),
                }
        if op not in ("record", "play"):
            raise ValueError("Unknown operation")
        if not self.audio_lock.acquire(False):
            raise ValueError("Audio busy; wait for the current operation")
        try:
            with tempfile.TemporaryDirectory(prefix="hardware-voice-") as tmp:
                path = str(Path(tmp) / "audio.wav")
                if op == "record":
                    seconds = data.get("duration_seconds", 5)
                    if type(seconds) is not int or not 1 <= seconds <= 20:
                        raise ValueError("duration_seconds must be 1–20")
                    subprocess.run(
                        [
                            "arecord",
                            "-D",
                            self.config["audio_device"],
                            "-q",
                            "-d",
                            str(seconds),
                            "-f",
                            "S16_LE",
                            "-r",
                            "16000",
                            "-c",
                            "1",
                            path,
                        ],
                        check=True,
                        capture_output=True,
                        timeout=seconds + 8,
                    )
                    raw = Path(path).read_bytes()
                    duration = validate_wav(raw)
                    return {
                        "wav_base64": base64.b64encode(raw).decode(),
                        "duration_seconds": duration,
                    }
                raw = base64.b64decode(data["wav_base64"], validate=True)
                duration = validate_wav(raw)
                Path(path).write_bytes(raw)
                start_at = data.get("start_at", time.time())
                delay = start_at - time.time()
                if not -5 <= delay <= 10:
                    raise ValueError("Invalid playback time; check Pi clock")
                if delay > 0:
                    time.sleep(delay)
                playback_started_at = time.time()
                subprocess.run(
                    ["aplay", "-D", self.config["audio_device"], "-q", path],
                    check=True,
                    capture_output=True,
                    timeout=duration + 8,
                )
                return {
                    "played": True,
                    "duration_seconds": duration,
                    "playback_started_at": playback_started_at,
                }
        finally:
            self.audio_lock.release()


def main():
    voice = Voice()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if self.path != "/rpc" or not 0 < n <= 1_500_000:
                    raise ValueError("Invalid request size or path")
                result = voice.request(json.loads(self.rfile.read(n)))
            except subprocess.CalledProcessError as exc:
                result = {"error": "Audio failed: " + exc.stderr.decode(errors="replace")[-500:]}
            except Exception as exc:
                result = {"error": str(exc)}
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    ThreadingHTTPServer(("127.0.0.1", voice.config["voice_port"]), Handler).serve_forever()


if __name__ == "__main__":
    main()

"""Button-triggered recording with a short renewable Mac lease (Python 3.7)."""

import base64
import signal
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path


class PushToTalk:
    def __init__(self, audio_lock, led, audio_device="default"):
        self.audio_lock, self.led = audio_lock, led
        self.audio_device = audio_device
        self.lock = threading.RLock()
        self.until = 0
        self.process = None
        self.ready = None
        self.error = None
        self.recording = False

    def control(self, enabled, acknowledge=None):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        with self.lock:
            self.until = time.monotonic() + 15 if enabled else 0
            if self.ready and acknowledge == self.ready["clip_id"]:
                self.ready = None
            if not enabled:
                self.stop()
            return {
                "armed": enabled,
                "recording": self.recording,
                "clip": self.ready,
                "error": self.error,
            }

    def stop(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.send_signal(signal.SIGINT)

    def button(self, pressed):
        with self.lock:
            if not pressed:
                self.stop()
                return
            if self.recording or self.ready or time.monotonic() >= self.until:
                return
            if not self.audio_lock.acquire(False):
                self.error = "Audio busy; try again after playback"
                return
            self.recording = True
            self.error = None
            try:
                self.tmp = tempfile.TemporaryDirectory(prefix="hardware-ptt-")
                path = Path(self.tmp.name) / "capture.wav"
                self.process = subprocess.Popen(
                    [
                        "arecord",
                        "-D",
                        self.audio_device,
                        "-q",
                        "-d",
                        "20",
                        "-f",
                        "S16_LE",
                        "-r",
                        "16000",
                        "-c",
                        "1",
                        str(path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                self.led.state = self.led.ON
                threading.Thread(target=self.finish, args=(path,), daemon=True).start()
            except Exception as exc:
                self.error = str(exc)
                if self.process and self.process.poll() is None:
                    self.process.kill()
                    self.process.wait()
                self.process = None
                self.recording = False
                self.audio_lock.release()
                self.led.state = self.led.OFF
                if hasattr(self, "tmp"):
                    self.tmp.cleanup()

    def finish(self, path):
        try:
            # Also stop on an expired Mac lease, even if the button stays down.
            while self.process.poll() is None:
                if time.monotonic() >= self.until:
                    self.stop()
                time.sleep(0.05)
            _, stderr = self.process.communicate(timeout=3)
            if not path.exists():
                raise RuntimeError(stderr.decode(errors="replace")[-300:])
            with wave.open(str(path)) as w:
                seconds = w.getnframes() / w.getframerate()
            if not 0.3 <= seconds <= 20.1:
                raise ValueError("Hold the button for at least half a second")
            with self.lock:
                self.ready = {
                    "clip_id": uuid.uuid4().hex,
                    "duration_seconds": seconds,
                    "wav_base64": base64.b64encode(path.read_bytes()).decode(),
                }
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
        finally:
            with self.lock:
                self.process = None
                self.recording = False
                self.led.state = self.led.OFF
                self.tmp.cleanup()
                self.audio_lock.release()

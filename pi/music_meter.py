"""Ephemeral local microphone energy meter. No recordings, text, or audio RPC."""

import array
import math
import os
import select
import subprocess
import sys
import threading
import time


class Energy:
    def __init__(self):
        self.average = 0.01

    def measure(self, raw):
        samples = array.array("h", raw)
        if sys.byteorder != "little":
            samples.byteswap()
        rms = math.sqrt(sum(float(x) * x for x in samples) / max(1, len(samples))) / 32768
        self.average = 0.96 * self.average + 0.04 * rms
        # Suppress silence; react to attacks relative to recent room volume.
        return round(
            min(1.0, max(0.0, (rms - max(0.006, self.average * 0.8)) / max(0.02, self.average))), 3
        )


class MusicMeter:
    def __init__(self, audio_lock, device):
        self.audio_lock, self.device = audio_lock, device
        self.guard = threading.RLock()
        self.until = 0
        self.blocked_until = 0
        self.process = None
        self.level = 0
        self.updated = 0
        self.error = None
        self.energy = Energy()
        threading.Thread(target=self.watch, daemon=True).start()

    def stop(self):
        with self.guard:
            if self.process is not None:
                proc, self.process = self.process, None
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                finally:
                    proc.stdout.close()
                    self.audio_lock.release()
            self.level = 0

    def preempt(self):
        with self.guard:
            self.blocked_until = time.monotonic() + 1
            self.stop()

    def control(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        with self.guard:
            self.until = time.monotonic() + 3 if enabled else 0
            if not enabled:
                self.stop()
            level, self.level = self.level, 0
            return {"active": self.process is not None, "level": level, "error": self.error}

    def watch(self):
        while True:
            with self.guard:
                now = time.monotonic()
                if now >= self.until:
                    self.stop()
                elif (
                    self.process is None
                    and now >= self.blocked_until
                    and self.audio_lock.acquire(False)
                ):
                    try:
                        self.process = subprocess.Popen(
                            [
                                "arecord",
                                "-D",
                                self.device,
                                "-q",
                                "-t",
                                "raw",
                                "-f",
                                "S16_LE",
                                "-r",
                                "16000",
                                "-c",
                                "1",
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            bufsize=0,
                        )
                        self.error = None
                    except Exception:
                        self.audio_lock.release()
                        self.error = "Music microphone unavailable"
                        self.blocked_until = now + 5
                proc = self.process
                if proc is not None:
                    if proc.poll() is not None:
                        self.stop()
                        self.error = "Music microphone unavailable"
                        self.blocked_until = now + 5
                    elif select.select([proc.stdout], [], [], 0)[0]:
                        raw = os.read(proc.stdout.fileno(), 1600)
                        if raw:
                            raw = raw[: len(raw) // 2 * 2]
                            self.level = max(self.level, self.energy.measure(raw))
            time.sleep(0.025)

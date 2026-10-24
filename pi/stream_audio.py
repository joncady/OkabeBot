"""Bounded PCM streaming playback; Python 3.7, one active stream, no retries."""

import base64
import os
import select
import subprocess
import threading
import time
import uuid


class StreamAudio:
    def __init__(self, audio_lock, device):
        self.audio_lock, self.device = audio_lock, device
        self.guard = threading.RLock()
        self.active = None
        threading.Thread(target=self.watch, daemon=True).start()

    def finish(self, abort=False):
        stream = self.active
        if stream is None:
            return {}
        self.active = None
        proc = stream["proc"]
        try:
            if abort:
                proc.kill()
            proc.stdin.close()
            proc.wait(timeout=35)
            if not abort and proc.returncode:
                raise RuntimeError("Streaming audio playback failed")
            return {
                "played": not abort,
                "duration_seconds": stream["bytes"] / 48000,
                "playback_started_at": stream["started"],
            }
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            self.audio_lock.release()

    def watch(self):
        while True:
            time.sleep(1)
            with self.guard:
                if self.active and time.monotonic() - self.active["updated"] > 15:
                    try:
                        self.finish(abort=True)
                    except Exception:
                        pass

    def request(self, data):
        with self.guard:
            op = data["op"]
            if op == "stream_start":
                if not self.audio_lock.acquire(False):
                    raise ValueError("Audio busy")
                try:
                    proc = subprocess.Popen(
                        [
                            "aplay",
                            "-D",
                            self.device,
                            "-q",
                            "-t",
                            "raw",
                            "-f",
                            "S16_LE",
                            "-r",
                            "24000",
                            "-c",
                            "1",
                        ],
                        stdin=subprocess.PIPE,
                        bufsize=0,
                        stderr=subprocess.DEVNULL,
                    )
                    os.set_blocking(proc.stdin.fileno(), False)
                    self.active = {
                        "id": uuid.uuid4().hex,
                        "proc": proc,
                        "bytes": 0,
                        "sequence": 0,
                        "started": None,
                        "updated": time.monotonic(),
                    }
                    return {"stream_id": self.active["id"]}
                except Exception:
                    self.audio_lock.release()
                    raise
            s = self.active
            if not s or data.get("stream_id") != s["id"]:
                raise ValueError("Unknown or expired stream")
            if op == "stream_abort":
                return self.finish(abort=True)
            if op == "stream_end":
                return self.finish()
            if op != "stream_chunk":
                raise ValueError("Unknown stream operation")
            if data.get("sequence") != s["sequence"]:
                raise ValueError("Out-of-order chunk; do not replay audio")
            raw = base64.b64decode(data["pcm_base64"], validate=True)
            if not raw or len(raw) > 48000 or len(raw) % 2 or s["bytes"] + len(raw) > 30 * 48000:
                raise ValueError("PCM chunk or stream exceeds limits")
            try:
                if s["started"] is None:
                    s["started"] = time.time()
                remaining = memoryview(raw)
                deadline = time.monotonic() + 5
                fd = s["proc"].stdin.fileno()
                while remaining:
                    wait = deadline - time.monotonic()
                    if wait <= 0 or not select.select([], [fd], [], wait)[1]:
                        raise TimeoutError("Speaker stopped accepting PCM")
                    try:
                        written = os.write(fd, remaining)
                    except BlockingIOError:
                        continue
                    if not written:
                        raise RuntimeError("Speaker pipe closed")
                    remaining = remaining[written:]
                s["bytes"] += len(raw)
                s["sequence"] += 1
                s["updated"] = time.monotonic()
                return {"accepted_bytes": len(raw), "playback_started_at": s["started"]}
            except Exception:
                self.finish(abort=True)
                raise

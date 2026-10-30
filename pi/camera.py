"""Bounded captures using rpicam, libcamera, or the legacy camera stack."""

import base64
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from device_config import load


class Camera:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(exist_ok=True)
        self.lock = threading.Lock()

    def executable(self, video):
        backend = load()["camera_backend"]
        candidates = {
            "rpicam": ("rpicam-still", "rpicam-vid"),
            "libcamera": ("libcamera-still", "libcamera-vid"),
            "legacy": ("raspistill", "raspivid"),
        }
        choices = ("rpicam", "libcamera", "legacy") if backend == "auto" else (backend,)
        for name in choices:
            if name not in candidates:
                raise ValueError("Unknown camera_backend")
            executable = candidates[name][int(video)]
            if shutil.which(executable):
                return executable, name
        raise RuntimeError("No supported camera application installed")

    def probe(self):
        """Low-resolution anonymous detection frame, stdout only: never writes an image."""
        if not self.lock.acquire(False):
            raise ValueError("Camera busy")
        try:
            executable, backend = self.executable(False)
            result = subprocess.run(
                [
                    executable,
                    "--nopreview",
                    "--timeout",
                    "700",
                    "--width",
                    "640",
                    "--height",
                    "480",
                    "--encoding",
                    "jpg",
                    "-o",
                    "-",
                ],
                check=True,
                capture_output=True,
                timeout=8,
            )
            if not 100 < len(result.stdout) <= 300000:
                raise ValueError("Invalid detection frame size")
            return {"jpeg_base64": base64.b64encode(result.stdout).decode("ascii")}
        finally:
            self.lock.release()

    def capture(self, video=False, duration_seconds=5, low_light=False):
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 20:
            raise ValueError("duration_seconds must be an integer from 1 to 20")
        if type(low_light) is not bool:
            raise ValueError("low_light must be boolean")
        if not self.lock.acquire(False):
            raise ValueError("Camera busy; wait for the current capture to finish")
        raw = None
        output = None
        try:
            if shutil.disk_usage(str(self.directory)).free < 100_000_000:
                raise ValueError("Insufficient free storage")
            if sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file()) > 200_000_000:
                raise ValueError(
                    "Camera archive exceeds 200 MB; copy or remove old recordings first"
                )
            executable, backend = self.executable(video)
            name = uuid.uuid4().hex
            if not video:
                output = self.directory / (name + ".jpg")
                args = [
                    executable,
                    "--nopreview",
                    "--timeout",
                    "2500",
                    "--width",
                    "1280",
                    "--height",
                    "960",
                    "-o",
                    str(output),
                ]
                if low_light:
                    args += ["-ex", "night"] if backend == "legacy" else ["--exposure", "long"]
                subprocess.run(args, check=True, capture_output=True, timeout=15)
                return {
                    "jpeg_base64": base64.b64encode(output.read_bytes()).decode("ascii"),
                    "low_light": low_light,
                }
            raw = self.directory / (name + ".h264")
            output = self.directory / (name + ".mp4")
            fps = 10 if low_light else 15
            args = [
                executable,
                "--nopreview",
                "--timeout",
                str(duration_seconds * 1000),
                "--width",
                "1280",
                "--height",
                "720",
                "--framerate",
                str(fps),
                "--bitrate",
                "2000000",
                "-o",
                str(raw),
            ]
            if low_light:
                args += ["-ex", "night"] if backend == "legacy" else ["--exposure", "long"]
            subprocess.run(args, check=True, capture_output=True, timeout=duration_seconds + 10)
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-r",
                    str(fps),
                    "-i",
                    str(raw),
                    "-c:v",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(output),
                ],
                check=True,
                capture_output=True,
                timeout=12,
            )
            if output.stat().st_size == 0:
                raise ValueError("Camera produced an empty recording")
            return {
                "filename": output.name,
                "bytes": output.stat().st_size,
                "requested_duration_seconds": duration_seconds,
                "fps": fps,
                "width": 1280,
                "height": 720,
                "audio": False,
                "low_light": low_light,
            }
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            if output and output.exists():
                output.unlink()
            details = getattr(exc, "stderr", b"") or b""
            raise RuntimeError("Camera capture failed: " + details.decode(errors="replace")[-700:])
        finally:
            if raw and raw.exists():
                raw.unlink()
            if not video and output and output.exists():
                output.unlink()
            self.lock.release()

"""Explicit opt-in budgets for disposable local recordings and diagnostic files.

Never scans databases, exports, backups, credentials, model/reference caches or
remote Pi storage. Snapshots contain counters, not filenames or file contents.
"""

import fcntl
import fnmatch
import os
from pathlib import Path
import stat
import threading
import time
from .presence_control import read, write

DEFAULTS = {
    "enabled": False,
    "recordings_days": 7,
    "recordings_mb": 256,
    "logs_days": 14,
    "logs_mb": 64,
}
LIMIT_FILES = 10000
GRACE_SECONDS = 120


def validate(value):
    if (
        not isinstance(value, dict)
        or set(value) != set(DEFAULTS)
        or type(value["enabled"]) is not bool
    ):
        raise ValueError("Use the private storage settings")
    for key in ("recordings_days", "logs_days"):
        if type(value[key]) is not int or not 1 <= value[key] <= 365:
            raise ValueError("Retention must be 1–365 days")
    for key in ("recordings_mb", "logs_mb"):
        if type(value[key]) is not int or not 1 <= value[key] <= 4096:
            raise ValueError("Budget must be 1–4096 MB")
    return dict(value)


class PrivateStorage:
    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = Path(folder).absolute(), clock
        self.path = self.folder / "storage-policy.json"
        self.lock = threading.RLock()
        self.last_cleanup = None
        self.scan_limited = False

    def policy(self):
        try:
            return validate({**DEFAULTS, **read(self.path, {})})
        except (ValueError, TypeError):
            return dict(DEFAULTS)  # Malformed policy must never enable deletion.

    def configure(self, value):
        with self.lock:
            write(self.path, validate(value))
            return self.snapshot()

    def files(self):
        # Only application-owned disposable locations and explicit extensions.
        patterns = (
            ("recordings", "audio", "*.wav"),
            ("recordings", "recordings", "*.mp4"),
            ("logs", "runtime", "*.log"),
            ("logs", "ptt", "transcript.jsonl"),
        )
        count = 0
        self.scan_limited = False
        for category, directory, pattern in patterns:
            parent = self.folder / directory
            if parent.is_symlink() or not parent.is_dir():
                continue
            try:
                with os.scandir(parent) as entries:
                    for entry in entries:
                        count += 1
                        if count > LIMIT_FILES:
                            self.scan_limited = True
                            return
                        if not fnmatch.fnmatchcase(entry.name, pattern):
                            continue
                        try:
                            info = entry.stat(follow_symlinks=False)
                            if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                                yield category, Path(entry.path), info
                        except OSError:
                            self.scan_limited = True
                            continue
            except OSError:
                self.scan_limited = True
                continue

    def snapshot(self):
        with self.lock:
            usage = {key: {"files": 0, "bytes": 0} for key in ("recordings", "logs")}
            for category, _, info in self.files():
                usage[category]["files"] += 1
                usage[category]["bytes"] += info.st_size
            return {
                "policy": self.policy(),
                "usage": usage,
                "scan_limit": LIMIT_FILES,
                "usage_complete": not self.scan_limited,
                "last_cleanup": self.last_cleanup,
                "scope": "Local audio/WAV, camera/MP4, runtime logs and PTT transcript log only; excludes databases, models, references, exports, backups and Pi files.",
            }

    def cleanup(self, *, busy=False):
        with self.lock:
            cfg = self.policy()
            if not cfg["enabled"] or busy:
                return
            self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            lockpath = self.folder / "storage-cleanup.lock"
            fd = os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
                result = {
                    "state": "complete",
                    "removed": 0,
                    "trimmed": 0,
                    "errors": 0,
                    "checked_at": self.clock(),
                }
                entries = list(self.files())
                now = self.clock()
                for category in ("recordings", "logs"):
                    selected = sorted(
                        (x for x in entries if x[0] == category), key=lambda x: x[2].st_mtime
                    )
                    total = sum(x[2].st_size for x in selected)
                    budget = cfg[category + "_mb"] * 1024 * 1024
                    cutoff = now - cfg[category + "_days"] * 86400
                    for _, path, old in selected:
                        if category == "recordings" and now - old.st_mtime < GRACE_SECONDS:
                            continue
                        excess = total - budget
                        if old.st_mtime >= cutoff and excess <= 0:
                            continue
                        try:
                            current = path.lstat()
                            if (
                                current.st_dev,
                                current.st_ino,
                                current.st_mtime_ns,
                                current.st_size,
                                current.st_nlink,
                            ) != (old.st_dev, old.st_ino, old.st_mtime_ns, old.st_size, 1):
                                continue
                            if category == "logs" and not path.name.endswith(".previous.log"):
                                # Copytruncate retains append-open descriptors. Keep only the tail;
                                # concurrent writes are best effort, not a transaction log guarantee.
                                keep = (
                                    0
                                    if old.st_mtime < cutoff
                                    else max(0, old.st_size - max(1, excess))
                                )
                                descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
                                with os.fdopen(descriptor, "r+b") as stream:
                                    check = os.fstat(stream.fileno())
                                    if (check.st_dev, check.st_ino, check.st_nlink) != (
                                        old.st_dev,
                                        old.st_ino,
                                        1,
                                    ):
                                        continue
                                    offset = max(0, check.st_size - keep)
                                    copied = 0
                                    while copied < keep:
                                        stream.seek(offset + copied)
                                        block = stream.read(min(1_048_576, keep - copied))
                                        if not block:
                                            break
                                        stream.seek(copied)
                                        stream.write(block)
                                        copied += len(block)
                                    stream.truncate(copied)
                                total -= old.st_size - copied
                                result["trimmed"] += 1
                            else:
                                path.unlink()
                                total -= old.st_size
                                result["removed"] += 1
                        except OSError:
                            result["errors"] += 1
                self.last_cleanup = result
            finally:
                os.close(fd)

"""Supervise optional speech workers and the controller without replaying actions."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .config import get_config, state_dir
from . import speech


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(value, f)
        temporary = Path(f.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def controller_state(folder, expected_pid=None):
    try:
        control = json.loads((folder / "ptt/control.json").read_text())
        if expected_pid is not None and control.get("pid") != expected_pid:
            return None
        url = urlsplit(control["url"])
        request = Request(
            urlunsplit((url.scheme, url.netloc, "/state", "", "")),
            headers={"X-Hardware-Token": url.fragment},
        )
        with urlopen(request, timeout=2) as response:
            return json.load(response)
    except Exception:
        return None


class Child:
    def __init__(self, name, argv, cwd, folder):
        self.name, self.argv, self.cwd, self.folder = name, argv, cwd, folder
        self.process = None
        self.attempts = 0
        self.retry_at = 0
        self.started = 0

    def start(self):
        if self.process and self.process.poll() is None:
            return
        if time.monotonic() < self.retry_at:
            return
        path = self.folder / (self.name + ".log")
        if path.exists() and path.stat().st_size > 5_000_000:
            path.replace(path.with_suffix(".previous.log"))
        try:
            with path.open("ab") as log:
                os.chmod(path, 0o600)
                self.process = subprocess.Popen(
                    self.argv,
                    cwd=self.cwd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    env=dict(os.environ, OKABEBOT_PARENT_PID=str(os.getpid())),
                )
            self.started = time.monotonic()
        except OSError:
            self.failed()

    def failed(self):
        self.attempts += 1
        self.retry_at = time.monotonic() + min(60, 2 ** min(self.attempts, 6))

    def running(self):
        return self.process is not None and self.process.poll() is None

    def check(self):
        if self.process and self.process.poll() is not None:
            self.process = None
            self.failed()
        if self.running() and time.monotonic() - self.started > 60:
            self.attempts = 0

    def stop(self):
        if self.running():
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                self.process = None
                return
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.process = None

    def snapshot(self):
        return {
            "running": self.running(),
            "pid": self.process.pid if self.running() else None,
            "restarts": self.attempts,
            "retry_in_s": max(0, round(self.retry_at - time.monotonic(), 1)),
        }


def supervise(config_path):
    config = get_config()
    folder = state_dir() / "runtime"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (folder / "supervisor.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("OkabeBot supervisor is already running") from None
    stopping = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.set())
    worker = Child("voice-worker", config["speech"]["worker_command"], config_path.parent, folder)
    bridge = Child(
        "controller",
        [sys.executable, "-m", "okabebot.bridge", "--config", str(config_path)],
        config_path.parent,
        folder,
    )
    managed = bool(worker.argv)
    warming_since = time.monotonic()
    failed_health = 0
    previous = None
    try:
        while not stopping.is_set():
            worker.check()
            bridge.check()
            if managed:
                worker.start()
            state = controller_state(state_dir(), bridge.process.pid) if bridge.running() else None
            busy = bool(
                state and (state.get("busy") or state.get("recording") or state.get("announcing"))
            )
            worker_ready = not managed
            if managed and worker.running():
                if busy:
                    worker_ready = True
                else:
                    try:
                        worker_ready = bool(speech.local_worker_status().get("ready"))
                    except Exception:
                        worker_ready = False
            if (
                worker_ready
                or time.monotonic() - warming_since
                > config["speech"]["worker_ready_timeout_seconds"]
            ):
                bridge.start()
            if managed and worker.running() and not busy:
                if worker_ready:
                    failed_health = 0
                elif (
                    time.monotonic() - worker.started
                    > config["speech"]["worker_ready_timeout_seconds"]
                ):
                    failed_health += 1
                    if failed_health >= 3:
                        worker.stop()
                        worker.failed()
                        failed_health = 0
            if state and state.get("codex_alive") is False and not busy:
                bridge.stop()
                bridge.failed()
            status = {
                "pid": os.getpid(),
                "updated_at": time.time(),
                "worker": worker.snapshot(),
                "controller": bridge.snapshot(),
                "worker_ready": worker_ready,
                "ready": bool(
                    state
                    and state.get("speech_health", {}).get("available")
                    and state.get("device_health", {}).get("voice", {}).get("available")
                    and state.get("codex_alive", True)
                ),
            }
            atomic_json(folder / "status.json", status)
            message = (
                "Ready"
                if status["ready"]
                else "Starting or recovering — check component status in the dashboard"
            )
            if message != previous:
                print(message, flush=True)
                if state:
                    try:
                        control = json.loads((state_dir() / "ptt/control.json").read_text())
                        print("Control page:", control["url"], flush=True)
                    except (OSError, ValueError, KeyError):
                        pass
                previous = message
            stopping.wait(3)
    finally:
        bridge.stop()
        if managed:
            worker.stop()
        atomic_json(
            folder / "status.json",
            {"pid": None, "ready": False, "stopped": True, "updated_at": time.time()},
        )


def install(config_path):
    if sys.platform != "darwin":
        raise SystemExit("Login service installation is macOS-only")
    label = "com.okabebot.controller." + hashlib.sha256(str(config_path).encode()).hexdigest()[:8]
    folder = Path.home() / "Library/LaunchAgents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (label + ".plist")
    logs = state_dir() / "runtime"
    logs.mkdir(parents=True, exist_ok=True)
    value = {
        "Label": label,
        "ProgramArguments": [
            sys.executable,
            "-m",
            "okabebot.runtime",
            "--config",
            str(config_path),
        ],
        "WorkingDirectory": str(config_path.parent),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        "StandardOutPath": str(logs / "supervisor.log"),
        "StandardErrorPath": str(logs / "supervisor.log"),
    }
    path.write_bytes(plistlib.dumps(value))
    os.chmod(path, 0o600)
    domain = "gui/" + str(os.getuid())
    subprocess.run(["launchctl", "bootout", domain + "/" + label], capture_output=True)
    # bootout can return while launchd is still removing the old job.
    for attempt in range(4):
        try:
            subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
            break
        except subprocess.CalledProcessError as exc:
            if exc.returncode != 5 or attempt == 3:
                raise
            time.sleep(2 ** attempt)
    print("Installed login service:", label)
    print("Stop with: launchctl bootout", domain + "/" + label)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("okabebot.local.json"))
    parser.add_argument(
        "--install", action="store_true", help="Install and start a macOS login service"
    )
    args = parser.parse_args()
    path = args.config.expanduser().resolve()
    os.environ["OKABEBOT_CONFIG"] = str(path)
    get_config.cache_clear()
    if args.install:
        install(path)
    else:
        supervise(path)


if __name__ == "__main__":
    main()

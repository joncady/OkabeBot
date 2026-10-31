"""One JSON-RPC transport for local devices and SSH-connected devices.

No remote shell scripts or automatic retries of hardware actions. Persistent SSH
forwarding lets the PTT loop poll cheaply while sharing the same HTTP protocol.
"""

from contextlib import contextmanager
import atexit
import threading
import json
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener

from .config import get_config

OPENER = build_opener(ProxyHandler({}))


def http_rpc(port, data, timeout=60):
    req = Request(
        f"http://127.0.0.1:{port}/rpc",
        json.dumps(data).encode(),
        {"Content-Type": "application/json"},
    )
    with OPENER.open(req, timeout=timeout) as response:
        return json.load(response)


class Device:
    def __init__(self, config):
        self.config = config

    def ssh_args(self):
        args = [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "ServerAliveInterval=5",
            "-o",
            "ServerAliveCountMax=2",
        ]
        if self.config["ssh_key"]:
            args += ["-i", self.config["ssh_key"], "-o", "IdentitiesOnly=yes"]
        return args

    def rpc(self, data):
        if self.config["transport"] == "local":
            return http_rpc(self.config["port"], data)
        # bridge.py is the same generic stdin bridge for either device service.
        script = self.config["remote_dir"] + "/bridge.py"
        command = "python3 " + shlex.quote(script) + " --port " + str(self.config["port"])
        result = subprocess.run(
            self.ssh_args() + [self.config["ssh_target"], command],
            input=json.dumps(data),
            text=True,
            capture_output=True,
            timeout=65,
        )
        if result.returncode or not result.stdout.strip():
            raise RuntimeError("Device SSH failed: " + result.stderr[-300:])
        return json.loads(result.stdout)

    def download(self, remote_path, destination):
        if self.config["transport"] == "local":
            shutil.copyfile(remote_path, destination)
            return
        command = "cat -- " + shlex.quote(str(remote_path))
        with Path(destination).open("wb") as output:
            subprocess.run(
                self.ssh_args() + [self.config["ssh_target"], command],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=45,
            )

    @contextmanager
    def connect(self, timeout=5):
        if self.config["transport"] == "local":
            yield lambda data: http_rpc(self.config["port"], data, timeout=timeout)
            return
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with tempfile.TemporaryFile() as errors:
            proc = subprocess.Popen(
                self.ssh_args()
                + [
                    "-N",
                    "-o",
                    "ExitOnForwardFailure=yes",
                    "-L",
                    f"127.0.0.1:{port}:127.0.0.1:{self.config['port']}",
                    self.config["ssh_target"],
                ],
                stderr=errors,
            )
            try:
                for _ in range(50):
                    if proc.poll() is not None:
                        errors.seek(0)
                        raise RuntimeError(
                            "SSH tunnel failed: " + errors.read().decode(errors="replace")[-300:]
                        )
                    try:
                        # Read-only health check; never retry an action.
                        http_rpc(port, {"op": "status"}, timeout=1)
                        break
                    except (OSError, ValueError):
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Device did not respond through SSH")

                def call(data):
                    if proc.poll() is not None:
                        raise RuntimeError("SSH disconnected; restart OkabeBot")
                    return http_rpc(port, data, timeout=timeout)

                yield call
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


class PooledDevice(Device):
    """One tunnel per endpoint/process. Never replay a failed operation."""

    def __init__(self, config, *, clock=time.monotonic):
        super().__init__(config)
        self._guard = threading.Lock()
        self._context = self._call = None
        self._clock = clock
        self._connect_failures = 0
        self._connect_after = 0

    def rpc(self, data):
        if self.config["transport"] == "local":
            return http_rpc(self.config["port"], data)
        with self._guard:
            if self._call is None:
                if self._clock() < self._connect_after:
                    raise RuntimeError(
                        "Device SSH is recovering; reconnect attempts are cooling down"
                    )
                try:
                    context = self.connect(timeout=65)
                    call = context.__enter__()
                except Exception:
                    # Waiting callers must not launch a fresh handshake storm.
                    # Only a later, separate request may try again; no RPC replay.
                    self._connect_failures = min(self._connect_failures + 1, 5)
                    self._connect_after = self._clock() + min(30, 2**self._connect_failures)
                    raise
                self._connect_failures = 0
                self._connect_after = 0
                self._context, self._call = context, call
            call = self._call
        try:
            return call(data)
        except Exception:
            # Drop a dead tunnel so the next request can reconnect. Never replay
            # this request: a physical action may have succeeded before timeout.
            with self._guard:
                if self._call is call:
                    context = self._context
                    self._context = self._call = None
                    context.__exit__(None, None, None)
            raise

    def close(self):
        with self._guard:
            if self._context is not None:
                self._context.__exit__(None, None, None)
                self._context = self._call = None


_devices = {}
_devices_lock = threading.Lock()


def device(name):
    config = get_config()["devices"][name]
    key = json.dumps(config, sort_keys=True)
    with _devices_lock:
        if key not in _devices:
            _devices[key] = PooledDevice(config)
        return _devices[key]


@atexit.register
def close_devices():
    for endpoint in list(_devices.values()):
        endpoint.close()

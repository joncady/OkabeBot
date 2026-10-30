"""Scoped HA TV preparation with nonce-bound completion and active-input verification."""

import json
from pathlib import Path
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class TVPreparation:
    def __init__(self, folder):
        self.path = Path(folder) / "tv-preparation.json"
        self.lock = threading.Lock()
        self.pending = {}

    def configured(self, destination):
        return self.path.exists() and destination in json.loads(self.path.read_text())

    def complete(self, value):
        if (
            not isinstance(value, dict)
            or set(value) != {"request_id", "status"}
            or value["status"] not in ("input_command_sent", "failed")
            or not isinstance(value["request_id"], str)
        ):
            raise ValueError("Invalid preparation completion")
        with self.lock:
            item = self.pending.get(value["request_id"])
            if not item or item["event"].is_set():
                return {"accepted": False}
            item["sent"] = value["status"] == "input_command_sent"
            item["event"].set()
            return {"accepted": True}

    def prepare(self, destination, verify_input, *, wake_cast=None):
        if not self.path.exists():
            return True  # Existing destinations retain their existing Cast behavior.
        bindings = json.loads(self.path.read_text())
        binding = bindings.get(destination)
        if binding is None:
            return True
        url = binding["url"]
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            return False
        timeout = binding.get("timeout_seconds", 45)
        if type(timeout) is not int or not 5 <= timeout <= 90:
            return False
        identity = secrets.token_urlsafe(24)
        item = {"event": threading.Event(), "sent": False}
        with self.lock:
            self.pending[identity] = item
        try:
            if mac := binding.get("wake_mac"):
                normalized = mac.replace(":", "").replace("-", "")
                address = bytes.fromhex(normalized)
                if len(address) != 6:
                    return False
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    packet = b"\xff" * 6 + address * 16
                    targets = [binding.get("wake_broadcast", "255.255.255.255")]
                    if host := binding.get("wake_host"):
                        targets.insert(0, host)
                    for target in dict.fromkeys(targets):
                        sender.sendto(packet, (target, 9))
            if binding.get("wake_cast") is True:
                if wake_cast is None or wake_cast() is not True:
                    return False
            with urlopen(
                Request(
                    url,
                    data=json.dumps({"request_id": identity}).encode(),
                    headers={"Content-Type": "application/json"},
                ),
                timeout=5,
            ) as response:
                if response.status not in (200, 202):
                    return False
            if not item["event"].wait(timeout) or not item["sent"]:
                return False
            # A successful remote key call is not proof the Chromecast is visible.
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                active = verify_input()
                if active is True or (
                    active is None and binding.get("allow_unknown_input") is True
                ):
                    return True
                time.sleep(0.5)
            return False
        except Exception:
            return False  # No raw webhook URLs or physical-action retries in logs.
        finally:
            with self.lock:
                self.pending.pop(identity, None)

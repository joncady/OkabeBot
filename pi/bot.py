"""Single-command BLE connections, with no automatic action retries."""

import re
import pexpect

from device_config import load

WRITE_UUID = "cba20002-224d-11e6-9fb8-0002a5d5c51b"
NOTIFY_UUID = "cba20003-224d-11e6-9fb8-0002a5d5c51b"


class Bot:
    def __init__(self):
        self.address = load()["switchbot_address"]

    def command(self, command):
        if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", self.address):
            raise ValueError("Set switchbot_address in device.local.json before using the Bot")
        child = pexpect.spawn(
            "gatttool", ["-b", self.address, "-t", "random", "-I"], encoding="utf-8", timeout=8
        )
        sent = False
        stage = "initializing"
        try:
            child.expect(r"\[LE\]>")
            child.sendline("connect")
            stage = "connecting"
            child.expect("Connection successful")
            child.expect(r"\[LE\]>")
            child.sendline("characteristics")
            stage = "discovering characteristics"
            child.expect(r"\[LE\]>")  # command prompt precedes async output
            child.expect(r"uuid[:=] ?" + WRITE_UUID)
            output = child.before + child.after
            write = re.search(
                r"char value handle[:=] ?(0x[0-9a-f]+), uuid[:=] ?" + WRITE_UUID, output
            )
            notify = re.search(
                r"char value handle[:=] ?(0x[0-9a-f]+), uuid[:=] ?" + NOTIFY_UUID, output
            )
            if not write or not notify:
                raise RuntimeError("Bot characteristics not found")
            notify_handle = int(notify.group(1), 16)
            child.expect(r"\[LE\]>")
            child.sendline("char-desc 0x%04x 0x%04x" % (notify_handle, notify_handle + 1))
            stage = "discovering notifications"
            child.expect(r"handle: (0x[0-9a-f]+), uuid: 00002902-0000-1000-8000-00805f9b34fb")
            cccd = child.match.group(1)
            child.sendline("char-write-req %s 0100" % cccd)
            stage = "subscribing"
            child.expect("Characteristic value was written successfully")
            sent = True  # any failure from this point has an ambiguous outcome
            stage = "waiting for command response"
            child.sendline("char-write-req %s %s" % (write.group(1), command))
            child.expect(r"Notification handle = 0x[0-9a-f]+ value: ([0-9a-f ]+)\r")
            raw = bytes.fromhex(child.match.group(1))
            return {
                "outcome": "confirmed" if raw[0] == 1 else "rejected",
                "status_code": raw[0],
                "raw": raw.hex(),
                "address": self.address,
            }
        except Exception as exc:
            return {
                "outcome": "unknown" if sent else "not_sent",
                "error": type(exc).__name__ + ": " + stage,
                "address": self.address,
            }
        finally:
            if child.isalive():
                child.sendline("disconnect")
                child.sendline("exit")
                child.close(force=True)

    def status(self):
        result = self.command("5702")
        if result["outcome"] == "confirmed":
            raw = bytes.fromhex(result["raw"])
            if len(raw) >= 10:
                result.update(
                    battery_percent=raw[1],
                    firmware=round(raw[2] / 10, 1),
                    mode="switch" if raw[9] & 0x10 else "press",
                )
        return result

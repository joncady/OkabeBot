"""Synthetic SSH failures; no network or physical operations."""

from contextlib import contextmanager
import unittest
from unittest.mock import patch

from okabebot.transport import PooledDevice


class BackoffTests(unittest.TestCase):
    def test_failed_handshake_rate_limit_recovery_and_reset(self):
        now = [0]
        device = PooledDevice({"transport": "ssh"}, clock=lambda: now[0])
        attempts, operations = [], []

        @contextmanager
        def connect(timeout):
            attempts.append(now[0])
            if len(attempts) in (1, 2, 4):
                raise OSError("no SSH greeting")
            yield lambda data: operations.append(data["op"]) or {"ok": True}

        with patch.object(device, "connect", connect):
            with self.assertRaises(OSError):
                device.rpc({"op": "press"})
            for _ in range(20):
                with self.assertRaises(RuntimeError):
                    device.rpc({"op": "status"})
            self.assertEqual(attempts, [0])
            now[0] = 2
            with self.assertRaises(OSError):
                device.rpc({"op": "status"})
            now[0] = 5
            with self.assertRaises(RuntimeError):
                device.rpc({"op": "status"})
            now[0] = 6
            self.assertEqual(device.rpc({"op": "status"}), {"ok": True})
            self.assertEqual(operations, ["status"])  # Failed press was never sent/replayed.
            device.close()
            with self.assertRaises(OSError):
                device.rpc({"op": "status"})
            self.assertEqual(device._connect_after, 8)  # Success reset the backoff.

    def test_failure_delay_is_bounded(self):
        now = [0]
        device = PooledDevice({"transport": "ssh"}, clock=lambda: now[0])
        with patch.object(device, "connect", side_effect=OSError("offline")):
            for expected in [2, 4, 8, 16, 30, 30]:
                with self.assertRaises(OSError):
                    device.rpc({"op": "status"})
                self.assertEqual(device._connect_after - now[0], expected)
                now[0] = device._connect_after

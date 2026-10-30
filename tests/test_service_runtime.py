import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import Mock
from okabebot.service_runtime import stopping, stop_process


class RuntimeTests(unittest.TestCase):
    def test_term_interrupts_wait_and_restores_handler(self):
        original = signal.getsignal(signal.SIGTERM)
        with stopping() as event:
            os.kill(os.getpid(), signal.SIGTERM)
            self.assertTrue(event.wait(0.01))
        self.assertEqual(signal.getsignal(signal.SIGTERM), original)

    def test_child_cleanup_escalates(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("fake", 5), 0]
        stop_process(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    def test_real_child_is_reaped(self):
        process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
        try:
            stop_process(process)
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

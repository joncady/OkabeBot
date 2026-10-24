import threading
import unittest
from unittest.mock import Mock, patch
from contextlib import contextmanager
from copy import deepcopy
from okabebot.config import DEFAULTS
from okabebot.transport import PooledDevice
from pi.stream_audio import StreamAudio


class LatencyTests(unittest.TestCase):
    def test_tunnel_reused_and_uncertain_action_not_replayed(self):
        config = deepcopy(DEFAULTS["devices"]["voice"])
        config["transport"] = "ssh"
        d = PooledDevice(config)
        call = Mock(side_effect=[{"ok": True}, TimeoutError("uncertain")])
        entered = []

        @contextmanager
        def connect(timeout):
            entered.append(timeout)
            yield call

        with patch.object(d, "connect", connect):
            self.assertEqual(d.rpc({"op": "status"}), {"ok": True})
            with self.assertRaises(TimeoutError):
                d.rpc({"op": "play"})
            self.assertEqual(len(entered), 1)
            self.assertEqual(call.call_count, 2)
            d.close()

    def test_stream_sequence_limit_and_lock_cleanup(self):
        with (
            patch("pi.stream_audio.threading.Thread"),
            patch("pi.stream_audio.os.set_blocking"),
            patch("pi.stream_audio.select.select", return_value=([], [1], [])),
            patch("pi.stream_audio.os.write", return_value=4) as write,
            patch("pi.stream_audio.subprocess.Popen") as popen,
        ):
            process = Mock(returncode=0)
            process.poll.return_value = 0
            popen.return_value = process
            lock = threading.Lock()
            stream = StreamAudio(lock, "default")
            sid = stream.request({"op": "stream_start"})["stream_id"]
            data = {"op": "stream_chunk", "stream_id": sid, "sequence": 0, "pcm_base64": "AAAAAA=="}
            stream.request(data)
            with self.assertRaises(ValueError):
                stream.request(data)
            write.assert_called_once()
            self.assertTrue(lock.locked())
            stream.request({"op": "stream_end", "stream_id": sid})
            self.assertFalse(lock.locked())
            with self.assertRaises(ValueError):
                stream.request(data)

    def test_cloud_does_not_request_without_key(self):
        from okabebot.speech import pcm_chunks

        with patch.dict("os.environ", {}, clear=True), patch("okabebot.speech.urlopen") as urlopen:
            with self.assertRaises(RuntimeError):
                list(pcm_chunks("hello", "happy", "warm"))
            urlopen.assert_not_called()

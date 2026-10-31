"""Portable full-path regression with deterministic model/PCM protocol doubles."""

import array
import base64
import collections
import copy
import io
import json
import math
from pathlib import Path
import socket
import sqlite3
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import wave

from okabebot.bridge import Bridge
from okabebot.config import DEFAULTS
from okabebot.local_conversation import LocalConversation
from okabebot.regression import Sandbox, check_pcm


class LocalEndToEndTests(unittest.TestCase):
    def test_clip_to_validated_action_to_streamed_speech_and_replay_suppression(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / "voice.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            listener.listen(1)
            self.addCleanup(listener.close)
            pcm = array.array(
                "h", [int(4000 * math.sin(i * 2 * math.pi * 300 / 24000)) for i in range(30720)]
            ).tobytes()
            requests = []

            def synthesize():
                connection, _ = listener.accept()
                with connection:
                    request = json.loads(connection.makefile("rb").readline())
                    requests.append(request)
                    for offset in range(0, len(pcm), 15360):
                        chunk = pcm[offset : offset + 15360]
                        connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                    connection.sendall(struct.pack("!I", 0))

            worker = threading.Thread(target=synthesize, daemon=True)
            worker.start()
            sandbox = Sandbox(folder)
            bridge = Bridge.__new__(Bridge)
            bridge.folder = folder
            bridge.lock = threading.RLock()
            bridge.messages = collections.deque(maxlen=100)
            bridge.timings = {}
            bridge.status = "Ready"
            bridge.show_activity = Mock()
            bridge.transcribe = Mock(return_value="Set speaker volume to 5 percent.")
            with sqlite3.connect(folder / "clips.sqlite3") as db:
                db.execute("CREATE TABLE clips (id TEXT PRIMARY KEY,status TEXT,transcript TEXT)")
            done = threading.Event()

            def notify(kind, data):
                bridge.notify(kind, data)
                if kind == "turn_completed":
                    done.set()

            settings = {
                "model": "protocol-double",
                "command": [
                    sys.executable,
                    str(Path(__file__).parent / "fixtures/fake_local_worker.py"),
                ],
            }
            spoken = []

            def voice_rpc(data):
                if data["op"] == "stream_start":
                    return {"stream_id": "test-stream"}
                if data["op"] == "stream_chunk":
                    spoken.append(base64.b64decode(data["pcm_base64"]))
                    return {"ok": True, "playback_started_at": time.time()}
                if data["op"] == "stream_end":
                    return {"played": True, "playback_started_at": time.time()}
                return {"ok": True}

            config = copy.deepcopy(DEFAULTS)
            config["speech"]["local_socket"] = str(path)
            with (
                patch("okabebot.speech.engine", return_value="local"),
                patch("okabebot.speech.get_config", return_value=config),
                patch("okabebot.character.state_dir", return_value=folder),
                patch("okabebot.timing.state_dir", return_value=folder),
                patch("okabebot.character.voice_rpc", side_effect=voice_rpc),
                patch("okabebot.audio_output.resolve", return_value={"target": "pi"}),
                patch("okabebot.character.display_rpc", return_value={"ok": True}),
            ):
                adapter = LocalConversation(
                    folder, notify, bridge.reply, executor=sandbox.execute, settings=settings
                )
                try:
                    adapter.policy = {
                        "auto_approve_hardware": True,
                        "allowed_tools": ["set_speaker_volume"],
                    }
                    bridge.codex = adapter
                    data = io.BytesIO()
                    with wave.open(data, "wb") as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(16000)
                        wav.writeframes(b"\0\0" * 1600)
                    clip = {
                        "clip_id": "e2e-once",
                        "released_at": time.time(),
                        "wav_base64": base64.b64encode(data.getvalue()).decode(),
                    }
                    bridge.handle_clip(clip)
                    self.assertTrue(done.wait(10), "Full local turn did not complete")
                    bridge.handle_clip(clip)
                    bridge.show_activity.assert_any_call("thinking")
                    self.assertEqual(len(sandbox.calls), 1)
                    self.assertEqual(sandbox.volume, 5)
                    self.assertEqual(requests[0]["text"], "Speaker volume is now 5 percent.")
                    self.assertEqual(b"".join(spoken), pcm)
                    self.assertTrue(all(len(c) <= 48000 and len(c) % 2 == 0 for c in spoken))
                    self.assertEqual(bridge.status, "Ready — hold the button to talk")
                    self.assertFalse(any(m["kind"] == "error" for m in bridge.messages))
                finally:
                    adapter.close()
            worker.join(timeout=1)

    def test_silent_pcm_regression_checks_reject_silence_and_accept_signal(self):
        with patch("okabebot.regression.speech.pcm_chunks", return_value=iter([b"\0\0" * 10000])):
            with self.assertRaises(ValueError):
                check_pcm("test")
        samples = array.array("h", [1000, -1000] * 6000).tobytes()
        with patch("okabebot.regression.speech.pcm_chunks", return_value=iter([samples])):
            result = check_pcm("test")
            self.assertEqual(result["rms"], 1000)

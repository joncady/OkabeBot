import base64
import importlib.util
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import sqlite3

from okabebot import bridge as mac
from okabebot.codex import Codex

spec = importlib.util.spec_from_file_location(
    "pi_ptt", Path(__file__).parents[1] / "pi/ptt_recorder.py"
)
pi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pi)


class PttTests(unittest.TestCase):
    def test_disarmed_expired_and_busy_never_start_microphone(self):
        voice = pi.PushToTalk(threading.Lock(), Mock())
        with patch.object(pi.subprocess, "Popen") as popen:
            voice.button(True)
            voice.control(True)
            voice.until = time.monotonic() - 1
            voice.button(True)
            voice.control(True)
            voice.audio_lock.acquire()
            voice.button(True)
            popen.assert_not_called()
        self.assertIn("busy", voice.error)

    def test_release_and_disarm_stop_recording(self):
        voice = pi.PushToTalk(threading.Lock(), Mock())
        voice.process = Mock()
        voice.process.poll.return_value = None
        voice.button(False)
        voice.process.send_signal.assert_called_once_with(pi.signal.SIGINT)
        voice.process.send_signal.reset_mock()
        voice.control(False)
        voice.process.send_signal.assert_called_once()

    def test_only_matching_ack_clears_recording(self):
        voice = pi.PushToTalk(threading.Lock(), Mock())
        voice.ready = {"clip_id": "one"}
        self.assertIsNotNone(voice.control(True, "wrong")["clip"])
        self.assertIsNone(voice.control(True, "one")["clip"])

    def test_uncertain_submission_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with sqlite3.connect(Path(tmp) / "clips.sqlite3") as db:
                db.execute("CREATE TABLE clips (id TEXT PRIMARY KEY, status TEXT, transcript TEXT)")
            bridge = mac.Bridge.__new__(mac.Bridge)
            bridge.folder = Path(tmp)
            bridge.show_activity = Mock()
            bridge.transcribe = Mock(return_value="What time is it?")
            bridge.notify = Mock()
            bridge.codex = Mock()
            bridge.codex.submit.side_effect = TimeoutError("uncertain")
            clip = {"clip_id": "one", "wav_base64": base64.b64encode(b"audio").decode()}
            with self.assertRaises(TimeoutError):
                bridge.handle_clip(clip)
            bridge.handle_clip(clip)
            bridge.codex.submit.assert_called_once()

    def test_rejected_or_failed_recording_clears_thinking_without_model_call(self):
        for transcript in ("", RuntimeError("transcription unavailable")):
            with self.subTest(transcript=str(transcript)), tempfile.TemporaryDirectory() as tmp:
                with sqlite3.connect(Path(tmp) / "clips.sqlite3") as db:
                    db.execute(
                        "CREATE TABLE clips (id TEXT PRIMARY KEY,status TEXT,transcript TEXT)"
                    )
                bridge = mac.Bridge.__new__(mac.Bridge)
                bridge.folder = Path(tmp)
                bridge.show_activity = Mock()
                bridge.notify = Mock()
                bridge.codex = Mock()
                bridge.transcribe = Mock()
                if isinstance(transcript, Exception):
                    bridge.transcribe.side_effect = transcript
                else:
                    bridge.transcribe.return_value = transcript
                clip = {"clip_id": "empty", "wav_base64": base64.b64encode(b"audio").decode()}
                if isinstance(transcript, Exception):
                    with self.assertRaises(RuntimeError):
                        bridge.handle_clip(clip)
                else:
                    bridge.handle_clip(clip)
                bridge.show_activity.assert_called_with("idle")
                bridge.codex.submit.assert_not_called()

    def test_approval_requires_explicit_supported_decision(self):
        client = Codex.__new__(Codex)
        client.lock = threading.RLock()
        client.send = Mock()
        client.approvals = {"1": {"id": 1, "method": "item/commandExecution/requestApproval"}}
        with self.assertRaises(ValueError):
            client.answer("1", "acceptForSession")
        client.send.assert_not_called()
        client.answer("1", "decline")
        client.send.assert_called_once_with({"id": 1, "result": {"decision": "decline"}})
        self.assertFalse(client.approvals)


if __name__ == "__main__":
    unittest.main()

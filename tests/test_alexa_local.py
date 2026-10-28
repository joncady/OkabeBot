import base64
import copy
import json
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from okabebot.alexa_local import render, LocalConversationServer, local_request


class LocalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.answer = {"text": "Air scatters blue light.", "audio_safe": True, "character": "okabe"}
        self.model = Mock()
        self.model.compose_alexa.side_effect = lambda *args: copy.deepcopy(self.answer)
        self.character = {"style": "okabe", "default_voice": "calm"}
        self.request = {
            "text": "Why is the sky blue?",
            "session": "a" * 64,
            "deadline": time.time() + 6,
        }

    def test_private_socket_roundtrip_encodes_selected_voice_without_playback(self):
        pcm = Mock(return_value=iter([b"\0\0" * 2400]))
        encoder = Mock(return_value=b"M" * 200)

        def renderer(*args):
            return render(*args, pcm=pcm, encode=encoder)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "conversation.sock"
            service = LocalConversationServer(
                path, self.model, lambda: self.character, renderer=renderer
            )
            try:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                result = local_request(path, self.request)
                self.assertTrue(result["audio_ready"])
                self.assertEqual(result["audio_duration_ms"], 100)
                self.assertEqual(base64.b64decode(result["mp3"]), b"M" * 200)
                pcm.assert_called_once_with(
                    self.answer["text"],
                    "neutral",
                    "calm",
                    character="okabe",
                    deadline=self.request["deadline"],
                )
                self.assertIn("first_pcm_s", result["timings"])
                with self.assertRaises(ValueError):
                    LocalConversationServer(path, self.model, lambda: self.character)
            finally:
                service.close()
            self.assertFalse(path.exists())

    def test_unsafe_answer_never_calls_synthesizer(self):
        self.answer["audio_safe"] = False
        pcm, encode = Mock(), Mock()
        result = render(
            self.model,
            "Question",
            "a" * 64,
            self.character,
            time.time() + 6,
            pcm=pcm,
            encode=encode,
        )
        self.assertFalse(result["audio_ready"])
        self.assertNotIn("mp3", result)
        pcm.assert_not_called()
        encode.assert_not_called()

    def test_failed_stage_is_reported_without_exception_message_or_content(self):
        self.model.compose_alexa.side_effect = ValueError("private utterance")
        with tempfile.TemporaryDirectory() as folder:
            service = LocalConversationServer(
                Path(folder) / "rpc.sock", self.model, lambda: self.character
            )
            try:
                result = local_request(service.path, self.request)
                self.assertEqual(result["error"], "ValueError")
                self.assertEqual(result["stage"], "model")
                self.assertGreaterEqual(result["elapsed_s"], 0)
                self.assertNotIn("private utterance", json.dumps(result))
            finally:
                service.close()

    def test_late_encoder_cannot_return_audio(self):
        now = time.time()
        current = [now]

        def late_encode(*args):
            current[0] = now + 7
            return b"M" * 200

        with patch("okabebot.alexa_local.time.time", side_effect=lambda: current[0]):
            with self.assertRaises(TimeoutError):
                render(
                    self.model,
                    "Question",
                    "a" * 64,
                    self.character,
                    now + 6,
                    pcm=lambda *a, **k: iter([b"\0\0"]),
                    encode=late_encode,
                )

    def test_unrecognized_local_operation_is_rejected_before_inference(self):
        renderer = Mock()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "conversation.sock"
            service = LocalConversationServer(
                path, self.model, lambda: self.character, renderer=renderer
            )
            try:
                with socket.socket(socket.AF_UNIX) as client:
                    client.connect(str(path))
                    client.sendall(b'{"op":"press_bot"}\n')
                    result = json.loads(client.makefile("rb").readline())
                self.assertEqual(result, {"error": "ValueError"})
                renderer.assert_not_called()
            finally:
                service.close()

    def test_rejects_public_directory_and_non_socket_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            parent.chmod(0o755)
            with self.assertRaises(PermissionError):
                LocalConversationServer(parent / "rpc.sock", self.model, lambda: self.character)
            parent.chmod(0o700)
            file = parent / "rpc.sock"
            file.write_text("preserve this file")
            with self.assertRaises(PermissionError):
                LocalConversationServer(file, self.model, lambda: self.character)
            self.assertEqual(file.read_text(), "preserve this file")

import array
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch
from okabebot import character as c
from pi.pip_face import render, EMOTIONS


class CharacterTests(unittest.TestCase):
    def test_silence_closes_mouth_and_loud_audio_opens_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "audio.wav"
            with wave.open(str(p), "wb") as w:
                w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                w.writeframes(array.array("h", [0] * 800 + [10000, -10000] * 400).tobytes())
            values, duration = c.envelope(p)
            self.assertEqual(values, [0, 1])
            self.assertAlmostEqual(duration, 0.1)

    def test_invalid_emotion_never_launches_synthesizer(self):
        with patch.object(c.speech.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                c.synthesize("hello", "bad", "pip", "unused")
            run.assert_not_called()

    def test_all_expressions_distinct_and_mouth_changes_frame(self):
        frames = [render(emotion=e, phase=1).tobytes() for e in EMOTIONS]
        self.assertEqual(len(set(frames)), 5)
        self.assertNotEqual(render(phase=1).tobytes(), render(phase=1, mouth=1).tobytes())

    def test_voice_preference_persists(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(c, "preference_path", return_value=Path(tmp) / "voice.json"),
        ):
            c.set_voice("robotic")
            self.assertEqual(c.current_voice(), "robotic")
            with self.assertRaises(ValueError):
                c.set_voice("invented")


class PlaybackSuppressionTests(unittest.TestCase):
    def test_mcp_speech_prevents_final_answer_replay(self):
        import io
        import json
        import threading
        from unittest.mock import Mock
        from okabebot.codex import Codex

        c = Codex.__new__(Codex)
        c.thread_id = "thread"
        c.turn_id = "turn"
        c.lock = threading.RLock()
        c.calls, c.approvals = {}, {}
        c.final, c.character_spoken, c.busy = [], False, True
        c.notify = Mock()
        done = threading.Event()
        replies = []
        c.completed = lambda text, status: (replies.append((text, status)), done.set())
        events = [
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread",
                    "item": {"type": "mcpToolCall", "tool": "character_speak"},
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread",
                    "item": {"type": "agentMessage", "phase": "final_answer", "text": "Hello!"},
                },
            },
            {
                "method": "turn/completed",
                "params": {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}},
            },
        ]
        c.process = Mock(stdout=io.StringIO("".join(json.dumps(e) + "\n" for e in events)))
        c.read()
        self.assertTrue(done.wait(1))
        self.assertEqual(replies, [("", "completed")])


class RendererAndSpeechTests(unittest.TestCase):
    def test_both_styles_support_expressions_and_palette(self):
        for style in ("okabe", "pip"):
            images = [render(style=style, emotion=e, phase=1).tobytes() for e in EMOTIONS]
            self.assertEqual(len(set(images)), 5)
            self.assertEqual(
                render(style=style, palette={"background": "#123456"}).getpixel((0, 0)),
                (18, 52, 86),
            )

    def test_linux_speech_uses_selected_preset_and_normalizes(self):
        from okabebot import speech

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(speech, "engine", return_value="espeak"),
            patch.object(speech, "voices", return_value={"calm": "en-gb"}),
            patch.object(speech.shutil, "which", return_value="/usr/bin/espeak-ng"),
            patch.object(speech.subprocess, "run") as run,
            patch.object(speech, "normalize") as normalize,
        ):
            target = Path(tmp) / "output.wav"
            speech.synthesize("Hello", "curious", "calm", target)
            command = run.call_args.args[0]
            self.assertEqual(command[:3], ["/usr/bin/espeak-ng", "-v", "en-gb"])
            self.assertIn("-f", command)
            normalize.assert_called_once()
            self.assertEqual(normalize.call_args.args[1], target)


class CharacterInstructionTests(unittest.TestCase):
    def test_resumed_turn_carries_current_character_and_original_transcript(self):
        from okabebot.codex import configured_input
        from okabebot.config import DEFAULTS
        from copy import deepcopy

        config = deepcopy(DEFAULTS)
        config["character"].update(name="Dot", persona="A cheerful robot.")
        with patch("okabebot.codex.get_config", return_value=config):
            prompt = configured_input("What is your name?")
        self.assertIn("current character name is Dot", prompt)
        self.assertIn("A cheerful robot.", prompt)
        self.assertTrue(prompt.endswith("[Microphone transcription]\nWhat is your name?"))

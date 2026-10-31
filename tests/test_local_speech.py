import json
import struct
import unittest
from unittest.mock import MagicMock, patch

from okabebot import speech


class LocalSpeechTests(unittest.TestCase):
    def consume(self, wire):
        peer = MagicMock()
        data = bytearray(wire)

        def receive(length):
            # Exercise partial reads, including partial frame headers.
            size = min(3, length, len(data))
            result = bytes(data[:size])
            del data[:size]
            return result

        peer.recv.side_effect = receive
        context = MagicMock()
        context.__enter__.return_value = peer
        with (
            patch.object(speech.socket, "socket", return_value=context),
            patch.object(
                speech, "get_config", return_value={"speech": {"local_socket": "/tmp/test.sock"}}
            ),
            patch("okabebot.profiles.current_character", return_value={"style": "kurisu"}),
        ):
            chunks = list(speech.local_pcm_chunks("Hello", "neutral", "warm"))
        request = json.loads(peer.sendall.call_args.args[0])
        self.assertEqual(request["character"], "kurisu")
        return chunks

    def test_fragmented_pcm_stream(self):
        self.assertEqual(self.consume(struct.pack("!I", 4) + b"1234" + b"\0" * 4), [b"1234"])

    def test_truncation_and_invalid_frame_abort(self):
        for wire in (struct.pack("!I", 4) + b"12", struct.pack("!I", 3), struct.pack("!I", 48002)):
            with self.subTest(wire=wire), self.assertRaises(RuntimeError):
                self.consume(wire)


class CharacterBackendTests(unittest.TestCase):
    def test_switching_characters_falls_back_locally_and_switches_back(self):
        profile = {"style": "kurisu"}
        with (
            patch.object(speech, "requested_engine", return_value="local"),
            patch.object(
                speech, "get_config", return_value={"speech": {"local_fallback": "system"}}
            ),
            patch.object(speech, "local_characters", return_value=("okabe", "kurisu")),
            patch.object(speech.platform, "system", return_value="Darwin"),
            patch("okabebot.profiles.current_character", side_effect=lambda: profile),
        ):
            for style, expected in [
                ("kurisu", "local"),
                ("sonic", "say"),
                ("pip", "say"),
                ("okabe", "local"),
                ("kurisu", "local"),
            ]:
                profile["style"] = style
                self.assertEqual(speech.engine(), expected)

    def test_outage_does_not_silently_change_a_supported_voice(self):
        with (
            patch.object(speech, "requested_engine", return_value="local"),
            patch.object(
                speech, "get_config", return_value={"speech": {"local_fallback": "system"}}
            ),
            patch.object(speech, "local_characters", side_effect=ConnectionError),
        ):
            self.assertEqual(speech.engine(), "local")

    def test_fallback_can_be_explicitly_disabled(self):
        with (
            patch.object(speech, "requested_engine", return_value="local"),
            patch.object(speech, "get_config", return_value={"speech": {"local_fallback": "none"}}),
            patch.object(speech, "local_characters") as capabilities,
        ):
            self.assertEqual(speech.engine(), "local")
            capabilities.assert_not_called()

    def test_system_fallback_produces_the_shared_pcm_contract_without_cloud(self):
        import wave

        pcm = b"\x01\x00" * 30000

        def synthesize(text, emotion, voice, target, sample_rate):
            self.assertEqual(sample_rate, 24000)
            with wave.open(str(target), "wb") as wav:
                wav.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
                wav.writeframes(pcm)

        with (
            patch.object(speech, "engine", return_value="say"),
            patch.object(speech, "synthesize", side_effect=synthesize),
            patch.object(speech, "urlopen") as cloud,
        ):
            chunks = list(speech.pcm_chunks("Hello", "neutral", "warm"))
        self.assertEqual(b"".join(chunks), pcm)
        self.assertTrue(all(0 < len(c) <= 24000 and len(c) % 2 == 0 for c in chunks))
        cloud.assert_not_called()

    def test_fallback_health_explains_effective_and_requested_backends(self):
        with (
            patch.object(speech, "engine", return_value="say"),
            patch.object(speech, "requested_engine", return_value="local"),
            patch.object(speech.shutil, "which", return_value="/usr/bin/say"),
        ):
            status = speech.health()
        self.assertTrue(status["available"])
        self.assertTrue(status["fallback"])
        self.assertEqual(status["requested_backend"], "local")
        self.assertEqual(status["backend"], "say")

    def test_capabilities_refresh_when_worker_endpoint_changes(self):
        import os
        import tempfile
        from pathlib import Path

        speech._local_characters.cache_clear()
        self.addCleanup(speech._local_characters.cache_clear)
        with tempfile.TemporaryDirectory() as folder:
            endpoint = Path(folder) / "voice.sock"
            endpoint.touch()
            with (
                patch.object(
                    speech, "get_config", return_value={"speech": {"local_socket": str(endpoint)}}
                ),
                patch.object(
                    speech,
                    "local_worker_status",
                    side_effect=[{"characters": ["kurisu"]}, {"characters": ["kurisu", "sonic"]}],
                ) as status,
            ):
                self.assertEqual(speech.local_characters(), ("kurisu",))
                self.assertEqual(speech.local_characters(), ("kurisu",))
                timestamp = endpoint.stat().st_mtime_ns + 1000000000
                os.utime(endpoint, ns=(timestamp, timestamp))
                self.assertEqual(speech.local_characters(), ("kurisu", "sonic"))
                self.assertEqual(status.call_count, 2)


class ReferenceManifestTests(unittest.TestCase):
    def test_speaker_only_text_uses_short_sentence_segments(self):
        import runpy
        from pathlib import Path

        split = runpy.run_path(str(Path(__file__).parents[1] / "scripts/qwen-voice-worker.py"))[
            "speaker_text"
        ]
        self.assertEqual(
            split("Rainy and cool outside. Bring a jacket if you head out."),
            "Rainy and cool outside.\nBring a jacket if you head out.",
        )
        self.assertIn("47.5", split("It is 47.5 degrees. Bring a jacket."))
        self.assertEqual(
            split("Cool outside, take a jacket—keep it handy"),
            "Cool outside.\nTake a jacket.\nkeep it handy.".replace("Take", "take"),
        )
        self.assertTrue(
            all(part[-1] in ".!?;" for part in split("An invented long phrase " * 30).splitlines())
        )
        self.assertTrue(
            all(len(part) <= 101 for part in split("A long invented sentence " * 30).splitlines())
        )

    def test_speaker_only_retries_truncation_without_publishing_bad_audio(self):
        import runpy
        from pathlib import Path
        from types import SimpleNamespace

        generate = runpy.run_path(str(Path(__file__).parents[1] / "scripts/qwen-voice-worker.py"))[
            "speaker_generate"
        ]
        model = MagicMock()
        good = SimpleNamespace(token_count=25)
        model.generate.side_effect = [[SimpleNamespace(token_count=75)], [good]]
        self.assertEqual(list(generate(model, "Stay curious.", {"temperature": 0.3})), [good])
        self.assertFalse(model.generate.call_args.kwargs["stream"])
        self.assertEqual(model.generate.call_args.kwargs["temperature"], 0.7)
        model.generate.side_effect = [
            [SimpleNamespace(token_count=75)],
            [SimpleNamespace(token_count=113)],
        ]
        with self.assertRaises(ValueError):
            list(generate(model, "Stay curious.", {}))

    def test_dense_numeric_clause_budget_uses_length_and_retry_has_headroom(self):
        import runpy
        from pathlib import Path
        from types import SimpleNamespace

        generate = runpy.run_path(str(Path(__file__).parents[1] / "scripts/qwen-voice-worker.py"))[
            "speaker_generate"
        ]
        model = MagicMock()
        clause = "2032-06-08 to 2032-06-09 (end exclusive)."
        model.generate.side_effect = lambda **kw: [SimpleNamespace(token_count=100)]
        self.assertEqual(len(list(generate(model, clause, {}))), 1)
        self.assertGreater(model.generate.call_args.kwargs["max_tokens"], 100)
        calls = []

        def capped(**kw):
            calls.append(kw["max_tokens"])
            return [SimpleNamespace(token_count=kw["max_tokens"] if len(calls) == 1 else 100)]

        model.generate.side_effect = capped
        self.assertEqual(len(list(generate(model, clause, {}))), 1)
        self.assertGreater(calls[1], calls[0])
        self.assertLessEqual(max(calls), 450)

    def test_modes_are_explicit_legacy_compatible_and_model_ready(self):
        import runpy
        import tempfile
        from pathlib import Path

        loader = runpy.run_path(str(Path(__file__).parents[1] / "scripts/qwen-voice-worker.py"))[
            "load_references"
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "references.json"
            (path.parent / "reference.wav").touch()
            path.write_text(
                json.dumps(
                    {
                        "first": {
                            "audio": "reference.wav",
                            "mode": "speaker_only",
                            "temperature": 0.3,
                        },
                        "second": {"audio": "reference.wav", "text": "Invented reference."},
                    }
                )
            )
            references = loader(path)
            self.assertIsNone(references["first"]["ref_text"])
            self.assertEqual(references["first"]["temperature"], 0.3)
            self.assertEqual(references["second"]["ref_text"], "Invented reference.")
            self.assertNotIn("temperature", references["second"])
            self.assertEqual(
                references["first"]["ref_audio"], str((path.parent / "reference.wav").resolve())
            )
            for invalid in (
                {},
                {"audio": "missing.wav", "mode": "speaker_only"},
                {"audio": "reference.wav"},
                {"audio": "reference.wav", "mode": "other"},
                {"audio": "reference.wav", "mode": "speaker_only", "text": "Unexpected ICL."},
                {"audio": "reference.wav", "mode": "speaker_only", "temperature": True},
            ):
                path.write_text(json.dumps({"first": invalid}))
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    loader(path)


if __name__ == "__main__":
    unittest.main()

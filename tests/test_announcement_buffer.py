import tempfile
import wave
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from okabebot import character as c


class AnnouncementTests(unittest.TestCase):
    def test_announcement_buffers_before_single_play_and_reply_still_streams(self):
        def synth(text, emotion, voice, path):
            with wave.open(str(path), "wb") as audio:
                audio.setparams((1, 2, 16000, 0, "NONE", "PCM"))
                audio.writeframes(b"\0\0" * 1600)

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(c, "state_dir", return_value=Path(folder)),
            patch.object(
                c,
                "current_character",
                return_value={"intensity": 0.5, "palette": {}, "style": "pip"},
            ),
            patch.object(c, "current_voice", return_value="calm"),
            patch.object(c.speech, "engine", return_value="local"),
            patch.object(c.speech, "synthesize", side_effect=synth) as synthesis,
            patch("okabebot.audio_output.resolve", return_value={"target": "pi"}),
            patch.object(c, "get_config", return_value={"speech": {"sync_lead_seconds": 0}}),
            patch.object(c.timing, "write"),
            patch.object(c, "display_rpc", return_value={}),
            patch.object(
                c,
                "voice_rpc",
                side_effect=[{"prepared_id": "fixture", "server_time": 123}, {"played": True}],
            ) as speaker,
            patch.object(c, "stream_speak", return_value={"spoken": True}) as streaming,
        ):
            connection = Mock()
            connection.__enter__ = Mock(return_value=speaker)
            connection.__exit__ = Mock(return_value=False)
            with patch.object(c, "device") as endpoint:
                endpoint.return_value.connect.return_value = connection
                result = c.speak("A synthetic greeting.", purpose="announcement")
            self.assertTrue(result["spoken"])
            self.assertEqual(speaker.call_args.args[0]["op"], "play_prepared")
            self.assertEqual(speaker.call_args_list[0].args[0]["op"], "audio_prepare")
            self.assertNotIn("wav_base64", speaker.call_args.args[0])
            self.assertEqual(speaker.call_args.args[0]["start_at"], 126)
            streaming.assert_not_called()
            synthesis.assert_called_once()
            c.speak("An interactive reply.", purpose="reply")
            streaming.assert_called_once()
            self.assertEqual(speaker.call_count, 2)

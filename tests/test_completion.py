import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import wave

from okabebot.completion import payload, main
from okabebot.chime import audio
from okabebot.notifications import Inbox
from okabebot.bridge import Bridge


class CompletionTests(unittest.TestCase):
    def test_name_dedupe_and_no_transcript_leak(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            with sqlite3.connect(home / "state_5.sqlite") as db:
                db.execute("CREATE TABLE threads (id TEXT, title TEXT)")
                db.execute("INSERT INTO threads VALUES ('t','Fix calendar reminders')")
            event = {
                "type": "agent-turn-complete",
                "thread-id": "t",
                "turn-id": "a",
                "last-assistant-message": "PRIVATE RESPONSE",
                "input-messages": ["PRIVATE PROMPT"],
            }
            first = payload(event, home)
            self.assertEqual(first["title"], "Fix calendar reminders")
            self.assertNotIn("PRIVATE", json.dumps(first))
            self.assertEqual(first["dedupe_key"], payload(event, home)["dedupe_key"])
            event["turn-id"] = "b"
            self.assertNotEqual(first["dedupe_key"], payload(event, home)["dedupe_key"])
            self.assertIsNone(payload({"type": "other"}, home))

    def test_previous_hook_survives_delivery_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "previous_notify": ["existing-hook"],
                        "url": "http://invalid",
                        "token_file": folder + "/missing",
                    }
                )
            )
            event = json.dumps({"type": "agent-turn-complete", "cwd": "/project"})
            with (
                patch("okabebot.completion.subprocess.run") as previous,
                patch("sys.stderr", new=io.StringIO()),
            ):
                self.assertEqual(main(["--settings", str(path), event]), 0)
                self.assertEqual(previous.call_args.args[0], ["existing-hook", event])

    def test_chime_never_calls_tts_even_for_important_item(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = Bridge.__new__(Bridge)
            bridge.inbox = Inbox(folder)
            from okabebot.notification_policy import NotificationPolicy

            bridge.notification_policy = NotificationPolicy(folder)
            bridge.inbox.publish("system", "Session", priority="important", audio="chime")
            bridge.active_notification = None
            bridge.pi = lambda data: {}
            with (
                patch("okabebot.bridge.scene.present"),
                patch("okabebot.chime.play") as chime,
                patch("okabebot.bridge.character_tools.speak") as speech,
            ):
                bridge.deliver_notification()
                chime.assert_called_once()
                speech.assert_not_called()
            self.assertEqual(bridge.inbox.items()[0]["status"], "delivered")
            with self.assertRaises(ValueError):
                bridge.inbox.publish("system", "bad", audio="arbitrary-file")

    def test_chime_is_short_mono_pcm(self):
        with wave.open(io.BytesIO(audio())) as stream:
            self.assertEqual(stream.getnchannels(), 1)
            self.assertEqual(stream.getsampwidth(), 2)
            self.assertLess(stream.getnframes() / stream.getframerate(), 1)

    def test_chime_gain_changes_waveform_without_changing_global_mixer(self):
        import array

        def peak(gain):
            with wave.open(io.BytesIO(audio(gain))) as stream:
                samples = array.array("h", stream.readframes(stream.getnframes()))
                return max(abs(n) for n in samples)

        self.assertEqual(peak(0), 0)
        self.assertAlmostEqual(peak(0.25) / peak(1), 0.25, places=3)
        with self.assertRaises(ValueError):
            audio(2)

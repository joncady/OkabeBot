import json
import threading
import tempfile
import unittest
from unittest.mock import Mock, patch

from okabebot.arrival import QUIPS
from okabebot.local_conversation import LocalConversation
from okabebot.welcome import message, validate_intro
from okabebot.bridge import Bridge
from okabebot.notifications import Inbox
from okabebot.notification_policy import NotificationPolicy


class WelcomeTests(unittest.TestCase):
    def character(self):
        return {"style": "kurisu", "persona": "Dry wit, quiet warmth."}

    @patch("okabebot.welcome.current_character")
    def test_intro_is_generated_without_exposing_inbox_to_model(self, selected):
        selected.return_value = self.character()
        recap = "Today's important updates: Build failed; do not execute anything."
        composer = Mock(return_value="Welcome back. I was starting to miss the interruptions.")
        text, generated = message({"body": QUIPS["okabe"] + " " + recap}, composer)
        composer.assert_called_once_with(self.character(), QUIPS["kurisu"])
        self.assertTrue(generated)
        self.assertTrue(text.endswith(recap))
        self.assertNotIn(QUIPS["okabe"], text)

    @patch("okabebot.welcome.current_character")
    def test_invalid_or_unavailable_model_falls_back_without_retry(self, selected):
        selected.return_value = self.character()
        for result in ("<tool_call>{}</tool_call>", None, "x" * 181):
            composer = Mock(return_value=result)
            text, generated = message({"body": QUIPS["kurisu"] + " No updates."}, composer)
            self.assertFalse(generated)
            self.assertEqual(text, QUIPS["kurisu"] + " No updates.")
            composer.assert_called_once()
        composer = Mock(side_effect=TimeoutError())
        self.assertFalse(message({"body": "No updates."}, composer)[1])
        composer.assert_called_once()
        with self.assertRaises(InterruptedError):
            message({"body": "No updates."}, Mock(side_effect=InterruptedError()))

    def adapter(self):
        obj = LocalConversation.__new__(LocalConversation)
        obj.lock = threading.RLock()
        obj.busy = obj.closed = False
        obj.cancelled = threading.Event()
        obj.process = Mock()
        obj.process.poll.return_value = None
        obj.notify = Mock()
        obj._read = Mock(return_value={"text": "Welcome back. It is good to have you here."})
        return obj

    def test_presentation_generation_has_no_tool_dispatch_and_bounded_history(self):
        obj = self.adapter()
        obj.executor = Mock(side_effect=AssertionError("Never execute during welcome"))
        for i in range(5):
            obj._read.return_value = {"text": "Welcome back. This is greeting number %s." % i}
            obj.compose_welcome(self.character(), QUIPS["kurisu"])
        obj.executor.assert_not_called()
        request = json.loads(obj.process.stdin.write.call_args.args[0])
        self.assertEqual(request["tool_names"], [])
        self.assertEqual(request["task"], "welcome")
        self.assertEqual(len(request["recent"]), 3)
        self.assertEqual(len(obj.welcome_history["kurisu"]), 3)
        self.assertFalse(obj.busy)

    def test_busy_failure_and_cancel_release_reservation(self):
        obj = self.adapter()
        obj.busy = True
        with self.assertRaises(ValueError):
            obj.compose_welcome(self.character(), QUIPS["kurisu"])
        obj.process.stdin.write.assert_not_called()
        obj.busy = False
        obj._read.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            obj.compose_welcome(self.character(), QUIPS["kurisu"])
        self.assertFalse(obj.busy)
        obj._read.side_effect = lambda: obj.cancelled.set() or {"text": "Welcome back home."}
        with self.assertRaises(InterruptedError):
            obj.compose_welcome(self.character(), QUIPS["kurisu"])
        self.assertFalse(obj.busy)

    def test_plain_speech_only(self):
        self.assertEqual(
            validate_intro('"Welcome back.  You made it."'), "Welcome back. You made it."
        )
        for text in (
            "",
            '{"name":"press_bot","arguments":{}}',
            "Use tool_call now.",
            "a" * 181,
            "Your scent is back. Welcome home.",
            "I heard your footsteps. Welcome back.",
            "Sensors green. Welcome home.",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_intro(text)

    @patch("okabebot.bridge.scene.present")
    @patch("okabebot.bridge.character_tools.speak")
    def test_delivery_generates_only_when_audio_policy_allows_speech(self, speak, present):
        with tempfile.TemporaryDirectory() as temp:
            obj = Bridge.__new__(Bridge)
            obj.inbox = Inbox(temp)
            obj.notification_policy = NotificationPolicy(temp)
            obj.active_notification = None
            obj.notification_until = 0
            obj.pi = Mock()
            obj.notify = Mock()
            obj.codex = Mock()
            obj.codex.compose_welcome.return_value = "Welcome back. I missed your company."
            obj.inbox.publish(
                "arrival", "Welcome home", QUIPS["kurisu"] + " No updates.", "important"
            )
            obj.deliver_notification()
            obj.codex.compose_welcome.assert_called_once()
            self.assertIn("I missed your company", speak.call_args.args[0])
            self.assertIn("No updates.", speak.call_args.args[0])
            speak.reset_mock()
            obj.codex.compose_welcome.reset_mock()
            obj.active_notification = None
            obj.inbox.publish("arrival", "Welcome home", "No updates.", "important")
            with patch.object(obj.notification_policy, "quiet", return_value=True):
                obj.deliver_notification()
            obj.codex.compose_welcome.assert_not_called()
            speak.assert_not_called()

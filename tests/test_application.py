import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from okabebot.application import Application
from okabebot.notifications import Inbox
from okabebot.notification_policy import NotificationPolicy
from okabebot.focus import FocusTimer
from okabebot.reminders import Reminders
from okabebot.echo import speak


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.inbox = Inbox(self.tmp.name)
        self.controller = SimpleNamespace(
            inbox=self.inbox,
            focus=FocusTimer(self.inbox),
            notification_policy=NotificationPolicy(self.tmp.name),
            pi=Mock(return_value={"percent": 5}),
            active_notification=None,
        )
        self.app = Application(self.controller)

    def test_volume_validation_and_actual_hardware_path(self):
        for value in [-1, 101, True, "5"]:
            with self.assertRaises(ValueError):
                self.app.execute("/speaker/volume", {"percent": value})
        self.controller.pi.assert_not_called()
        self.assertEqual(self.app.execute("/speaker/volume", {"percent": 5}), {"percent": 5})
        self.controller.pi.assert_called_once_with({"op": "volume", "percent": 5})

    def test_snooze_and_source_preferences_preserve_other_rules(self):
        self.app.execute(
            "/notifications/preferences",
            {"sources": {"calendar": {"enabled": True, "audio": "silent"}}},
        )
        self.app.execute(
            "/notifications/preferences",
            {"sources": {"github": {"enabled": False, "audio": "default"}}},
        )
        result = self.app.execute("/notifications/snooze", {"minutes": 60})
        self.assertTrue(result["snoozed"])
        self.assertEqual(len(result["sources"]), 2)
        self.assertFalse(self.app.execute("/notifications/snooze", {"minutes": 0})["snoozed"])
        with self.assertRaises(ValueError):
            self.app.execute("/notifications/snooze", {"minutes": True})

    def test_reminders_are_durable_deduplicated_and_isolated_from_focus(self):
        first = self.app.execute(
            "/reminders/create", dict(text="Check oven", minutes=20, request_id="request-1234")
        )
        second = self.app.execute(
            "/reminders/create", dict(text="Check oven", minutes=20, request_id="request-1234")
        )
        self.assertEqual(first["id"], second["id"])
        reminders = Reminders(Inbox(self.tmp.name)).list()
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["audio"], "chime")
        focus = self.app.execute("/focus/start", {"minutes": 25})
        self.assertFalse(self.app.execute("/reminders/cancel", {"id": focus["id"]})["cancelled"])
        self.assertTrue(self.app.execute("/reminders/cancel", {"id": first["id"]})["cancelled"])
        self.assertEqual(self.app.execute("/reminders/list", {})["reminders"], [])
        self.assertTrue(self.controller.focus.status()["active"])

    def test_dismiss_updates_screen_and_inbox(self):
        item = self.inbox.publish("github", "Build failed")
        self.controller.active_notification = item
        with patch("okabebot.application.scene.dismiss") as dismiss:
            self.app.execute("/notifications/dismiss", {"id": item["id"]})
            dismiss.assert_called_once()
        self.assertIsNone(self.controller.active_notification)
        self.assertEqual(self.inbox.items()[0]["status"], "dismissed")

    def test_focus_cancel_same_state_as_dashboard(self):
        self.app.execute("/focus/start", {"minutes": 5})
        self.assertTrue(self.controller.focus.status()["active"])
        self.assertFalse(self.app.execute("/focus/cancel", {})["active"])

    def test_reply_waits_for_destination_and_announcements_do_not_follow(self):
        moving = {"current_location": None, "locations": []}
        arrived = {
            "current_location": "phone",
            "locations": [{"id": "phone", "audio_target": "device"}],
        }
        self.controller.surfaces = Mock()
        self.controller.surfaces.snapshot.side_effect = [moving, arrived]
        self.controller.surface_audio = Mock()
        self.controller.surface_audio.ready.return_value = True
        with (
            patch("okabebot.audio_output.target", return_value="pi"),
            patch("okabebot.application.time.sleep"),
        ):
            self.assertEqual(
                self.app.execute("/audio/resolve", {"purpose": "reply"}),
                {"target": "browser", "device_id": "phone", "ready": True},
            )
            self.assertEqual(
                self.app.execute("/audio/resolve", {"purpose": "announcement"}), {"target": "pi"}
            )
        self.assertEqual(self.controller.surfaces.snapshot.call_count, 2)

    def test_unsettled_transfer_fails_without_redirecting_speech(self):
        self.controller.surfaces = Mock()
        self.controller.surfaces.snapshot.return_value = {"current_location": None}
        with (
            patch("okabebot.audio_output.target", return_value="pi"),
            patch("okabebot.application.time.monotonic", side_effect=[0, 9]),
        ):
            with self.assertRaisesRegex(ValueError, "still moving"):
                self.app.execute("/audio/resolve", {"purpose": "reply"})
        with patch("okabebot.controller_tools.request", side_effect=ValueError("handoff failed")):
            from okabebot.audio_output import resolve

            with self.assertRaisesRegex(ValueError, "handoff failed"):
                resolve("reply")


class EchoTests(unittest.TestCase):
    def env(self, name):
        return {
            "OKABEBOT_ECHO_SPEAKERS": json.dumps({"Show": "notify.show_speak"}),
            "OKABEBOT_ECHO_WEBHOOK": "http://127.0.0.1:8123/api/webhook/private",
        }.get(name, "")

    @patch("okabebot.echo.env_value")
    @patch("okabebot.echo.urlopen")
    def test_explicit_target_dry_run_and_escaped_soft_speech(self, opened, env):
        env.side_effect = self.env
        with self.assertRaises(ValueError):
            speak("Unknown", "Hello")
        self.assertTrue(speak("Show", "Hello", dry_run=True)["dry_run"])
        opened.assert_not_called()
        result = speak("Show", "<loud> & hi")
        self.assertTrue(result["accepted"])
        self.assertFalse(result["playback_confirmed"])
        payload = json.loads(opened.call_args.args[0].data)
        self.assertEqual(payload["speaker"], "notify.show_speak")
        self.assertIn("&lt;loud&gt; &amp; hi", payload["message"])
        self.assertIn('volume="soft"', payload["message"])

    @patch("okabebot.echo.env_value")
    @patch("okabebot.echo.urlopen", side_effect=TimeoutError("private url"))
    def test_failure_is_not_retried_or_leaked(self, opened, env):
        env.side_effect = self.env
        with self.assertRaisesRegex(ValueError, "outcome unknown"):
            speak("Show", "Hello")
        self.assertEqual(opened.call_count, 1)

"""Synthetic post-tool composition; commands execute once and never from reply text."""

import json
import threading
import unittest
from unittest.mock import Mock, patch
from okabebot.local_conversation import LocalConversation
from okabebot.tool_reply import facts, acceptable


class ReplyTests(unittest.TestCase):
    def test_missing_home_sensor_explains_selected_coverage_without_inventing_value(self):
        from okabebot.tool_reply import preserve_scope

        result = {"queried_source": "home_devices", "items": []}
        text = preserve_scope("It is 72 degrees.", "get_context_feed", result)
        self.assertIn("sensor", text)
        self.assertIn("selected", text)
        self.assertNotIn("72", text)
        stale = {"queried_source": "home_devices", "items": [{"fresh": False}]}
        text = preserve_scope("It is 72 degrees now.", "get_context_feed", stale)
        self.assertIn("older", text)
        self.assertNotIn("72", text)

    def test_calendar_scope_label_cannot_replace_empty_or_populated_answer(self):
        from okabebot.local_conversation import acknowledgement

        empty = {
            "available": True,
            "start_date": "2032-06-08",
            "end_date": "2032-06-09",
            "events": [],
        }
        for text in (
            "Configured calendar feed.",
            "Your connected calendar.",
            "Calendar view for today.",
            "Configured calendar feed, 2032-06-08 to 2032-06-09 (end exclusive). No events in this view; other calendars are not included.",
        ):
            reply, used = self.adapter(text).render_tool_reply(
                "Calendar today?",
                "get_calendar_agenda",
                empty,
                acknowledgement("get_calendar_agenda", empty),
            )
            self.assertFalse(used)
            self.assertIn("don't see any events", reply)
            self.assertNotIn("exclusive", reply)
            self.assertNotIn("Configured", reply)
        natural = "I don't see any events in the connected calendar today."
        self.assertTrue(acceptable(natural, "get_calendar_agenda", empty, ""))
        populated = {**empty, "events": [{"title": "Imaginary planning session", "start": "10 AM"}]}
        self.assertFalse(
            acceptable(
                "Your connected calendar is available.", "get_calendar_agenda", populated, ""
            )
        )
        self.assertTrue(
            acceptable(
                "Imaginary planning session is at 10 AM in the connected calendar.",
                "get_calendar_agenda",
                populated,
                "10 AM",
            )
        )
        self.assertIn(
            "Imaginary planning session", acknowledgement("get_calendar_agenda", populated)
        )
        self.assertNotIn(
            "don't see any events",
            acknowledgement("get_calendar_agenda", {"available": False, "events": []}),
        )

    def adapter(self, result):
        obj = LocalConversation.__new__(LocalConversation)
        obj.process = Mock()
        obj.cancelled = threading.Event()
        obj._read = Mock(return_value={"text": result})
        return obj

    def test_human_house_summary_preserves_coverage_without_reciting_fields(self):
        actual = {
            "coverage": "partial",
            "period": "today",
            "observations": [
                {"kind": "notification", "text": "Invented doorbell rang"},
                {"kind": "appliance", "text": "Invented washer: finished"},
            ],
        }
        text = "The doorbell rang and the washer finished. That's all I can see from the connected records."
        obj = self.adapter(text)
        reply, used = obj.render_tool_reply(
            "What happened at home?", "get_home_activity", actual, "Partial records available."
        )
        self.assertTrue(used)
        self.assertEqual(reply, text)
        request = json.loads(obj.process.stdin.write.call_args.args[0])
        self.assertEqual(request["task"], "tool_reply")
        self.assertEqual(request["tool_names"], [])
        self.assertNotIn("observed_at", request["text"])

    def test_unsupported_claims_and_executable_output_fall_back(self):
        actual = {"coverage": "partial", "observations": []}
        for text in (
            "Everything is fine.",
            '{"tool_call":{"name":"press_bot"}}',
            "The house is safe.",
            "I saw 47 visitors in the records, but only limited history.",
        ):
            reply, used = self.adapter(text).render_tool_reply(
                "House status", "get_home_activity", actual, "No connected history."
            )
            self.assertFalse(used)
            self.assertEqual(reply, "No connected history.")

    def test_accepted_actions_are_not_arrival_or_playback_proof(self):
        self.assertFalse(
            acceptable(
                "I've arrived at the TV.", "move_companion", {"accepted": True}, "Heading to TV."
            )
        )
        self.assertTrue(
            acceptable(
                "I'm heading to the TV.", "move_companion", {"accepted": True}, "Heading to TV."
            )
        )
        self.assertFalse(
            acceptable(
                "Spotify is playing now.",
                "control_spotify",
                {},
                "Playback is not independently confirmed.",
            )
        )

    def test_credentials_ids_urls_and_nested_transport_are_not_model_context(self):
        value = facts(
            "get_recent_notifications",
            {
                "token": "private",
                "url": "https://private.test",
                "notifications": [
                    {
                        "title": "Invented update",
                        "id": "private-id",
                        "body": "Untrusted body",
                        "transport": {"secret": "private"},
                    }
                ],
            },
            "One update.",
        )
        text = json.dumps(value)
        self.assertNotIn("private", text)
        self.assertIn("Untrusted body", text)

    def test_failure_after_action_never_calls_executor_again(self):
        obj = self.adapter("")
        obj._read.side_effect = RuntimeError("worker disconnected")
        obj.executor = Mock()
        reply, used = obj.render_tool_reply(
            "Lower volume",
            "set_speaker_volume",
            {"percent": 10},
            "Speaker volume is now 10 percent.",
        )
        self.assertFalse(used)
        self.assertEqual(reply, "Speaker volume is now 10 percent.")
        obj.executor.assert_not_called()

    def test_opt_out_skips_rendering_model(self):
        obj = self.adapter("Should not be used")
        with patch("okabebot.profiles.personality", return_value={"natural_tool_replies": False}):
            self.assertEqual(
                obj.render_tool_reply(
                    "Volume", "set_speaker_volume", {"percent": 10}, "Volume is 10."
                ),
                ("Volume is 10.", False),
            )
        obj._read.assert_not_called()

    def test_clock_paraphrase_and_scope_qualification_are_not_discarded(self):
        from okabebot.tool_reply import preserve_scope

        data = {"coverage": "partial", "observations": []}
        reply = preserve_scope("The TV was reported off at 5:50 PM.", "get_home_activity", data)
        self.assertTrue(acceptable(reply, "get_home_activity", data, "A TV reported off at 17:50."))
        self.assertIn("only", reply)
        self.assertFalse(
            acceptable(
                "The TV turned off. These are partial records.",
                "get_home_activity",
                data,
                "TV reported off.",
            )
        )

    def test_missing_alerts_do_not_become_a_claim_none_triggered(self):
        from okabebot.tool_reply import preserve_scope

        reply = preserve_scope(
            "The TV was reported off. No alerts triggered.",
            "get_home_activity",
            {"coverage": "partial"},
        )
        self.assertNotIn("No alerts triggered", reply)
        self.assertIn("TV was reported off", reply)

    def test_state_readings_cannot_become_a_people_or_empty_home_claim(self):
        from okabebot.tool_reply import preserve_scope

        reply = preserve_scope(
            "The TV was reported off. No one was detected in the house.",
            "get_home_activity",
            {"coverage": "partial"},
        )
        self.assertNotIn("No one", reply)
        self.assertIn("TV was reported off", reply)
        data = facts(
            "get_home_activity",
            {
                "coverage": "partial",
                "observations": [{"kind": "presence", "text": "Household presence unknown"}],
            },
            "Partial history",
        )
        self.assertEqual(data["observations"], [])

    def test_abbreviated_match_title_does_not_lose_its_second_half(self):
        from okabebot.tool_reply import preserve_scope

        result = {"coverage": "partial"}
        text = "YouTube reported a video about Rovers vs. United. That's only the connected history I have."
        self.assertIn("Rovers vs. United", preserve_scope(text, "get_home_activity", result))

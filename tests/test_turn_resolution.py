"""Invented date windows and distinct notification identities; no providers."""

import datetime as dt
import unittest

from okabebot.turn_resolution import (
    ResolutionError,
    calendar_window,
    notification_arguments,
    notification_intent,
)


class CalendarResolutionTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2032, 6, 8, 18, tzinfo=dt.timezone.utc).timestamp()  # Tuesday

    def window(self, text, **kwargs):
        return calendar_window(text, now=self.now, timezone="UTC", **kwargs)

    def test_spoken_range_has_exclusive_api_end_and_accepts_month_shorthand(self):
        expected = {"start_date": "2032-06-10", "end_date": "2032-06-13"}
        for text in (
            "From June 10 through June 12",
            "Between Jun 10 and June 12",
            "Between June 10 and 12",
            "June 10 to 12",
            "2032-06-10 through 2032-06-12",
            "June 10–12",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.window(text), expected)
        self.assertEqual(self.window("June 10 until June 12")["end_date"], "2032-06-12")
        self.assertEqual(
            self.window('start_date="2032-06-10" end_date="2032-06-12"')["end_date"], "2032-06-12"
        )
        self.assertEqual(self.window("June 10 to June 12 exclusive")["end_date"], "2032-06-12")

    def test_weekday_followup_inherits_requested_week_not_today(self):
        task = {
            "tool": "get_calendar_agenda",
            "arguments": {"start_date": "2032-06-23", "end_date": "2032-06-24"},
        }
        self.assertEqual(
            self.window("And Thursday?", task=task),
            {"start_date": "2032-06-24", "end_date": "2032-06-25"},
        )
        self.assertEqual(self.window("And tomorrow?", task=task)["start_date"], "2032-06-09")
        self.assertEqual(self.window("And the 25th?", task=task)["start_date"], "2032-06-25")
        self.assertEqual(self.window("Thursday")["start_date"], "2032-06-10")
        self.assertEqual(self.window("next Thursday")["start_date"], "2032-06-17")
        self.assertEqual(self.window("this Monday")["start_date"], "2032-06-07")

    def test_ambiguous_or_invalid_dates_clarify_instead_of_guessing(self):
        for text in (
            "June 31",
            "2032-19-04",
            "June 12 through June 10",
            "June 10 and June 12",
            "June 10 and 12",
            "Tuesday and Friday",
            "today or tomorrow",
        ):
            with self.subTest(text=text), self.assertRaises(ResolutionError):
                self.window(text)
        self.assertEqual(self.window("What's on my calendar?"), {})

    def test_local_midnight_year_rollover_and_weekend_range(self):
        now = dt.datetime(2032, 1, 1, 1, tzinfo=dt.timezone.utc).timestamp()
        result = calendar_window("today", now=now, timezone="America/Los_Angeles")
        self.assertEqual(result["start_date"], "2031-12-31")
        self.assertEqual(
            self.window("December 30 through January 2"),
            {"start_date": "2032-12-30", "end_date": "2033-01-03"},
        )
        self.assertEqual(
            self.window("Saturday through Monday"),
            {"start_date": "2032-06-12", "end_date": "2032-06-15"},
        )
        self.assertEqual(
            self.window("next month"), {"start_date": "2032-07-01", "end_date": "2032-08-01"}
        )


class NotificationResolutionTests(unittest.TestCase):
    def test_source_and_sender_are_distinct_typed_targets(self):
        self.assertEqual(
            notification_intent("Disable rail notifications."),
            {"name": "set_notification_source", "arguments": {"source": "rail", "enabled": False}},
        )
        self.assertEqual(
            notification_intent("Set mail notifications from sender team-demo to silent."),
            {
                "name": "set_sender_notification_rule",
                "arguments": {"source": "mail", "sender_id": "team-demo", "audio": "silent"},
            },
        )
        self.assertEqual(
            notification_intent("For forge notifications, make sender bot-demo urgent.")[
                "arguments"
            ],
            {"source": "forge", "sender_id": "bot-demo", "priority": "urgent"},
        )
        with self.assertRaises(ResolutionError):
            notification_arguments(
                "Set mail notifications from sender team-demo to silent.",
                "set_notification_source",
                {"source": "team-demo", "audio": "silent"},
            )

    def test_unrequested_model_options_are_removed_and_legacy_fields_can_be_preserved(self):
        text = "Disable rail notifications."
        self.assertEqual(
            notification_arguments(
                text,
                "set_notification_source",
                {"source": "rail", "enabled": False, "audio": "silent"},
            ),
            {"source": "rail", "enabled": False},
        )
        self.assertEqual(
            notification_arguments(
                "Make forge notifications silent.",
                "set_notification_source",
                {"source": "forge", "enabled": True, "audio": "silent"},
                current_rule={"enabled": False, "audio": "chime"},
            ),
            {"source": "forge", "enabled": False, "audio": "silent"},
        )
        with self.assertRaises(ResolutionError):
            notification_arguments(
                text, "set_notification_source", {"source": "transit", "enabled": False}
            )

    def test_identity_words_are_not_configuration_values(self):
        self.assertEqual(
            notification_intent("Make silent notifications silent.")["arguments"],
            {"source": "silent", "audio": "silent"},
        )
        self.assertEqual(
            notification_intent("Make MAIL notifications from sender urgent urgent.")["arguments"],
            {"source": "mail", "sender_id": "urgent", "priority": "urgent"},
        )
        self.assertEqual(
            notification_intent("Disable urgent-alerts notifications.")["arguments"],
            {"source": "urgent-alerts", "enabled": False},
        )
        self.assertEqual(
            notification_intent(
                "Set mail notifications from sender silent-bot priority important."
            )["arguments"],
            {"source": "mail", "sender_id": "silent-bot", "priority": "important"},
        )

    def test_how_to_quotes_and_ambiguous_targets_do_not_authorize_actions(self):
        for text in (
            "How do I disable mail notifications?",
            "Someone said 'disable rail notifications'",
            "I like silent notifications",
            "Don't disable rail notifications.",
        ):
            self.assertEqual(notification_intent(text), {})
        for text in (
            "Please disable notifications from sender team-demo.",
            "Disable rail notifications and enable mail notifications.",
            "Set rail notifications to speech and silent.",
            "Set mail notifications from sender bot-demo not urgent.",
            "Disable rail notifications until tomorrow.",
            "Make rail notifications silent for 10 minutes.",
            "Enable rail alerts if someone arrives.",
        ):
            with self.subTest(text=text), self.assertRaises(ResolutionError):
                notification_intent(text)


class ActionFramingTests(unittest.TestCase):
    def test_primary_current_speech_act_not_reported_or_quoted_payload(self):
        from okabebot.turn_resolution import assert_action_request

        valid = [
            ("Please help: set speaker volume to 20 percent", "set_speaker_volume"),
            ("Could you please pause Spotify?", "control_spotify"),
            ('On Echo Desk, say "Tea is ready"', "speak_on_echo"),
            ('Say "set volume to 100 percent" on Echo Desk', "speak_on_echo"),
            ("Please remind me to 'set volume to 100 percent' in ten minutes", "create_reminder"),
            (
                "For forge notifications, make sender bot-demo urgent",
                "set_sender_notification_rule",
            ),
            ("Show my agenda for tomorrow", "show_calendar_agenda"),
            ("I would like you to move to Desk nook", "move_companion"),
        ]
        for text, tool in valid:
            with self.subTest(text=text):
                self.assertIsNone(assert_action_request(text, tool))
        invalid = [
            ("Someone said 'set volume to 100 percent'", "set_speaker_volume"),
            ('Say "set volume to 100 percent" on Echo Desk', "set_speaker_volume"),
            ("On Echo Desk, say set speaker volume to 100 percent", "set_speaker_volume"),
            ('Set a reminder to "set volume to 100 percent"', "set_speaker_volume"),
            ("What would happen if I set volume to 100 percent?", "set_speaker_volume"),
            ("Please don't set speaker volume to 100 percent", "set_speaker_volume"),
            ("Explain how to disable rail notifications", "set_notification_source"),
            ("Tell me about Echo Desk", "speak_on_echo"),
            ("Send an announcement to Living room TV", "move_companion"),
            ("I said move to Living room TV", "move_companion"),
            ("For example, set speaker volume to 100 percent", "set_speaker_volume"),
            ("In theory, set speaker volume to 100 percent", "set_speaker_volume"),
            ("For example, disable rail notifications", "set_notification_source"),
            ("For instance, say hello on Echo Loft", "speak_on_echo"),
        ]
        for text, tool in invalid:
            with self.subTest(text=text), self.assertRaises(ResolutionError):
                assert_action_request(text, tool)

    def test_speaker_uses_explicit_full_registry_name_not_model_abbreviation(self):
        from okabebot.turn_resolution import resolve_named_speaker

        names = ["Echo", "Echo Loft", "Echo Desk", "Jonathan's 2nd Echo"]
        for text, requested, expected in [
            ('Say "Tea is ready" on Echo Loft.', "Loft", "Echo Loft"),
            ('On Echo Desk, say "Tea is ready".', "Desk", "Echo Desk"),
            ('Please help: on Echo Loft, say "set volume to 100".', "Echo", "Echo Loft"),
            ('Say "Echo Loft is offline" on Echo Desk.', "Loft", "Echo Desk"),
            ('On "Echo Loft", say "Hello".', "Loft", "Echo Loft"),
            ('Tell Echo Loft "Hello".', "Loft", "Echo Loft"),
            ('Say "Hello" on Jonathan’s 2nd Echo.', "2nd Echo", "Jonathan's 2nd Echo"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(resolve_named_speaker(text, requested, names), expected)
        for text in [
            'Say "Use Echo Loft".',
            'Say "hello on Echo Loft".',
            "Say 'don't speak on Echo Loft'.",
            'On paper, say "Hello" on Echo Loft.',
            'Say "Hello" on Loft.',
            'Say "Hello" on Echo Loft and Echo Desk.',
            'On Echo Loft, say "hello" on Echo Desk.',
            'Someone said "Say hello on Echo Desk".',
            "Tell me about what is on Echo Loft.",
            "Say the lights on Echo Loft are working.",
        ]:
            with self.subTest(text=text), self.assertRaises(ResolutionError):
                resolve_named_speaker(text, "Echo Loft", names)


class ReviewBoundaryTests(unittest.TestCase):
    def test_notification_configuration_consumes_the_whole_supported_command(self):
        from okabebot.turn_resolution import assert_action_request

        for text in [
            'Set the label to "mute mail notifications"',
            'Set the reminder text to "disable mail notifications"',
            'Make a card that says "disable mail notifications"',
        ]:
            with self.subTest(text=text):
                self.assertEqual(notification_intent(text), {})
                with self.assertRaises(ResolutionError):
                    assert_action_request(text, "set_notification_source")
        for text in [
            "Mute notifications from mail for a week",
            "Disable mail notifications in five minutes",
            "Disable mail notifications once I leave",
            "Make mail notifications silent but keep urgent ones audible",
            "Disable mail notifications; only the noisy ones",
            "Set mail notifications to silent and delete my reminder",
            "Disable mail notifications and send a message to my boss",
            "Disable mail notifications during meetings",
            "Disable mail notifications whenever I leave",
            'Set mail notifications to "disable mail notifications"',
        ]:
            with self.subTest(text=text), self.assertRaises(ResolutionError):
                notification_intent(text)
        self.assertEqual(
            notification_intent('Set "mail" notifications to "silent"')["arguments"],
            {"source": "mail", "audio": "silent"},
        )

    def test_one_explicit_calendar_year_propagates_before_rollover_and_date_validation(self):
        now = dt.datetime(2032, 6, 8, tzinfo=dt.timezone.utc).timestamp()

        def window(text):
            return calendar_window(text, now=now, timezone="UTC")

        for text in [
            "Calendar February 4, 2033 through February 6",
            "Calendar February 4 through February 6, 2033",
        ]:
            self.assertEqual(window(text), {"start_date": "2033-02-04", "end_date": "2033-02-07"})
        self.assertEqual(
            window("December 30, 2033 through January 2"),
            {"start_date": "2033-12-30", "end_date": "2034-01-03"},
        )
        self.assertEqual(
            window("December 30 through January 2, 2034"),
            {"start_date": "2033-12-30", "end_date": "2034-01-03"},
        )
        self.assertEqual(
            window("December 30, 2031 through February 29"),
            {"start_date": "2031-12-30", "end_date": "2032-03-01"},
        )
        for text in [
            "Read my calendar tomorrow, not June 11.",
            "Check today instead of June 12",
            'My note says "June 10"',
            'My note says "Thursday"',
            'My note says "start_date=2033-02-04 end_date=2033-02-07"',
        ]:
            with self.subTest(text=text), self.assertRaises(ResolutionError):
                window(text)
        self.assertEqual(
            window('What is on my calendar tomorrow? My note says "June 10"'),
            {"start_date": "2032-06-09", "end_date": "2032-06-10"},
        )

    def test_immediate_actions_never_drop_scheduling_or_conditions(self):
        from okabebot.turn_resolution import assert_action_request

        for text, name in [
            ('On Echo Loft, say "hello" in five minutes', "speak_on_echo"),
            ("Set speaker volume to 20 percent once I leave", "set_speaker_volume"),
            ("Remind me if the garage opens", "create_reminder"),
            ("Snooze notifications whenever I leave", "snooze_notifications"),
            ("Show my agenda once I get home", "show_calendar_agenda"),
            ('Say "hello" on Echo Loft at five', "speak_on_echo"),
            ('Say "hello" on Echo Loft on Monday', "speak_on_echo"),
            ('Say "hello" on Echo Loft every morning', "speak_on_echo"),
            ('Say "hello" on Echo Loft as soon as I arrive', "speak_on_echo"),
            ('Remind me to "check the stove" every morning', "create_reminder"),
        ]:
            with self.subTest(text=text), self.assertRaises(ResolutionError):
                assert_action_request(text, name)
        for text, name in [
            ('On Echo Loft, say "If I leave, wave goodbye"', "speak_on_echo"),
            ('Remind me to "check if the garage opens" in five minutes', "create_reminder"),
            ("Snooze notifications for twenty minutes", "snooze_notifications"),
            ("Show my agenda for tomorrow", "show_calendar_agenda"),
            ("Show my agenda for Monday", "show_calendar_agenda"),
            ("Show my agenda for June 10 until June 12", "show_calendar_agenda"),
            ('Say "We meet Monday at five every week" on Echo Loft', "speak_on_echo"),
        ]:
            with self.subTest(text=text):
                self.assertIsNone(assert_action_request(text, name))


class ImmediateConvenienceTests(unittest.TestCase):
    def test_pause_resume_and_exact_rule_patch(self):
        for text, expected in [
            (
                "Pause notifications for an hour and a half.",
                {"name": "snooze_notifications", "arguments": {"minutes": 90}},
            ),
            (
                "Let notifications through again.",
                {"name": "snooze_notifications", "arguments": {"minutes": 0}},
            ),
            (
                "Keep notifications from forge enabled but silent.",
                {
                    "name": "set_notification_source",
                    "arguments": {"source": "forge", "enabled": True, "audio": "silent"},
                },
            ),
            (
                "For forge sender bot-demo, set priority to important.",
                {
                    "name": "set_sender_notification_rule",
                    "arguments": {
                        "source": "forge",
                        "sender_id": "bot-demo",
                        "priority": "important",
                    },
                },
            ),
        ]:
            with self.subTest(text=text):
                self.assertEqual(notification_intent(text), expected)
        for text in [
            "Pause notifications for two hours if I leave",
            "Pause notifications for two hours tomorrow",
        ]:
            with self.assertRaises(ResolutionError):
                notification_intent(text)

    def test_payload_is_not_movement_and_imperatives_keep_guardrails(self):
        from okabebot.local_conversation import shortlist, READ_TOOLS, TARGETS
        from okabebot.turn_resolution import assert_action_request

        specs = {*READ_TOOLS, *TARGETS}
        self.assertEqual(
            shortlist('On Echo Loft, say "never move to the TV".', specs), ["speak_on_echo"]
        )
        for text, tool in [
            ("Please give me a 25-minute focus block.", "control_focus_session"),
            ("Go to the next Spotify track.", "control_spotify"),
            ("Press SwitchBot once now.", "press_bot"),
        ]:
            self.assertEqual(shortlist(text, specs), [tool])
            self.assertIsNone(assert_action_request(text, tool))
        for text, tool in [
            ("Give me a focus session whenever I leave", "control_focus_session"),
            ("Go to the next Spotify track after I arrive", "control_spotify"),
            ("Press SwitchBot once I leave", "press_bot"),
        ]:
            with self.assertRaises(ResolutionError):
                assert_action_request(text, tool)

    def test_pause_arguments_come_from_current_request_not_model_duration(self):
        from okabebot.local_conversation import validate_call

        name = "snooze_notifications"
        specs = {
            name: {
                "parameters": {
                    "type": "object",
                    "properties": {"minutes": {"type": "integer"}},
                    "required": ["minutes"],
                }
            }
        }
        policy = {"auto_approve_hardware": True, "allowed_tools": [name]}
        self.assertEqual(
            validate_call(
                "Pause notifications for an hour and a half",
                {"name": name, "arguments": {"minutes": 900}},
                specs,
                policy,
                "synthetic",
            )[1],
            {"minutes": 90},
        )

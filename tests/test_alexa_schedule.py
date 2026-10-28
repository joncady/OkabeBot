"""Exercise the shipped HA template and persistent notification contract offline."""

import datetime as dt
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import jinja2
import yaml

from okabebot.notifications import Inbox


class PackageLoader(yaml.SafeLoader):
    pass


PackageLoader.add_constructor("!secret", lambda loader, node: "private-placeholder")
PACKAGE = yaml.load(
    (Path(__file__).parents[1] / "examples/home-assistant/alexa.yaml").read_text(),
    Loader=PackageLoader,
)
NOW = dt.datetime(2026, 10, 26, 12, tzinfo=dt.timezone.utc)
FUTURE = "2026-10-26T12:10:00+00:00"


def timestamp(value, default=0):
    try:
        return (
            value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value)
        ).timestamp()
    except (ValueError, TypeError):
        return default


class AlexaScheduleTests(unittest.TestCase):
    def condition(
        self, old="unavailable", new=FUTURE, entity="sensor.show_next_timer", imported=True
    ):
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.globals.update(
            integration_entities=lambda domain: [entity] if imported else [],
            as_timestamp=timestamp,
            now=lambda: NOW,
        )
        data = dict(
            entity_id=entity,
            old_state=None if old is None else SimpleNamespace(state=old),
            new_state=None if new is None else SimpleNamespace(state=new),
        )
        return (
            env.from_string(PACKAGE["automation"][0]["conditions"][0]["value_template"])
            .render(trigger=SimpleNamespace(event=SimpleNamespace(data=SimpleNamespace(**data))))
            .strip()
            == "True"
        )

    def test_real_idle_to_future_transitions_include_reminders(self):
        self.assertTrue(self.condition())
        self.assertTrue(self.condition(old="unknown", entity="sensor.echo_next_reminder"))
        self.assertTrue(self.condition(old="2026-10-26T12:05:00+00:00"))

    def test_startup_removal_cancel_past_and_unrelated_changes_are_ignored(self):
        for args in (
            dict(old=None),
            dict(new=None),
            dict(new="unknown"),
            dict(new="unavailable"),
            dict(new="2026-10-26T11:59:00+00:00"),
            dict(old=FUTURE),
            dict(imported=False),
            dict(entity="sensor.outside_next_timer", imported=False),
            dict(entity="sensor.show_next_alarm"),
        ):
            with self.subTest(args=args):
                self.assertFalse(self.condition(**args))

    def test_cards_are_silent_and_reconnect_schedule_is_persistently_deduped(self):
        env = jinja2.Environment()
        env.filters["to_json"] = json.dumps
        env.globals.update(as_timestamp=timestamp, now=lambda: NOW)
        template = PACKAGE["rest_command"]["okabebot_alexa_notification"]["payload"]
        payload = json.loads(
            env.from_string(template).render(
                title="Alexa timer scheduled",
                body="Show · Timer at 12:10 PM.",
                event_key="alexa-schedule-sensor.show_next_timer-1793016600",
            )
        )
        self.assertEqual(payload["source"], "alexa")
        self.assertEqual(payload["audio"], "silent")
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("okabebot.notifications.time.time", return_value=NOW.timestamp()),
        ):
            first = Inbox(folder).publish(**payload)
            replay = Inbox(folder).publish(**payload)
            self.assertEqual(first["id"], replay["id"])
        action = PACKAGE["automation"][0]["actions"][-1]
        self.assertEqual(action["action"], "rest_command.okabebot_alexa_notification")


class AlexaVoiceTemplateTests(unittest.TestCase):
    def test_voice_gate_ignores_unmapped_old_initial_and_attribute_only_events(self):
        import re

        package = yaml.load(
            (Path(__file__).parents[1] / "examples/home-assistant/alexa_voice.yaml").read_text(),
            Loader=PackageLoader,
        )
        automation = package["automation"][0]
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.filters["regex_replace"] = lambda value, pattern, replacement: re.sub(
            pattern, replacement, value
        )
        env.globals.update(now=lambda: NOW, as_timestamp=timestamp)
        template = env.from_string(automation["conditions"][1]["value_template"])
        for command, old, state, expected in [
            ("I'm home", "old", NOW.isoformat(), True),
            ("call companion to laptop", "old", NOW.isoformat(), True),
            ("play music", "old", NOW.isoformat(), False),
            ("I'm home", None, NOW.isoformat(), False),
            ("I'm home", NOW.isoformat(), NOW.isoformat(), False),
            ("I'm home", "old", (NOW - dt.timedelta(minutes=2)).isoformat(), False),
        ]:
            trigger = SimpleNamespace(
                entity_id="event.test_voice_event",
                from_state=None if old is None else SimpleNamespace(state=old),
                to_state=SimpleNamespace(state=state, attributes={"voice_command": command}),
            )
            with self.subTest(command=command, old=old, state=state):
                self.assertEqual(
                    template.render(
                        trigger=trigger,
                        **{
                            **automation["variables"],
                            "command": command,
                            "source_timestamp_ms": timestamp(state) * 1000,
                        },
                    ).strip()
                    == "True",
                    expected,
                )

    def test_request_subtitle_is_opt_in_and_requires_the_generic_request_marker(self):
        package = yaml.load(
            (Path(__file__).parents[1] / "examples/home-assistant/alexa_voice.yaml").read_text(),
            Loader=PackageLoader,
        )
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        template = env.from_string(package["automation"][0]["variables"]["command"])
        for opted_in, title, subtitle, expected in [
            (True, "Request", "I'm home.", "I'm home."),
            (False, "Request", "I'm home.", "Request"),
            (True, "play music", "I'm home.", "play music"),
        ]:
            trigger = SimpleNamespace(
                entity_id="event.echo_voice_event",
                to_state=SimpleNamespace(
                    attributes={"voice_command": title, "voice_reply": subtitle}
                ),
            )
            with self.subTest(opted_in=opted_in, title=title):
                value = template.render(
                    trigger=trigger,
                    request_subtitle_entities=["event.echo_voice_event"] if opted_in else [],
                ).strip()
                self.assertEqual(value, expected)

    def test_missing_or_old_source_time_cannot_use_fresh_ha_receipt_time(self):
        package = yaml.load(
            (Path(__file__).parents[1] / "examples/home-assistant/alexa_voice.yaml").read_text(),
            Loader=PackageLoader,
        )
        env = jinja2.Environment()
        env.filters["regex_replace"] = __import__("re").sub
        # Match HA filter argument order.
        import re

        env.filters["regex_replace"] = lambda value, pattern, replacement: re.sub(
            pattern, replacement, value
        )
        env.globals.update(as_timestamp=timestamp, now=lambda: NOW)
        automation = package["automation"][0]
        template = env.from_string(automation["conditions"][1]["value_template"])
        trigger = SimpleNamespace(
            from_state=SimpleNamespace(state="old"), to_state=SimpleNamespace(state=NOW.isoformat())
        )
        for source in (None, True, (NOW.timestamp() - 3600) * 1000):
            with self.subTest(source=source):
                result = template.render(
                    trigger=trigger,
                    **{
                        **automation["variables"],
                        "command": "I'm home",
                        "source_timestamp_ms": source,
                    },
                ).strip()
                self.assertEqual(result, "False")

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from jinja2 import Environment
import yaml


class SecretLoader(yaml.SafeLoader):
    pass


SecretLoader.add_constructor("!secret", lambda loader, node: loader.construct_scalar(node))


class HeartbeatTests(unittest.TestCase):
    def test_event_driven_worn_uses_independent_heartbeat(self):
        source = yaml.load(
            Path("examples/home-assistant/presence_follow.yaml").read_text(), Loader=SecretLoader
        )
        text = source["automation"][0]["actions"][0]["data"]["payload"]
        env = Environment()
        env.filters["to_json"] = json.dumps
        template = env.from_string(text)
        for worn, heartbeat, reported, expected in (
            ("on", "50", 990, True),
            ("off", "50", 990, False),
            ("on", "50", 600, None),
            ("on", "unavailable", 990, None),
            ("unknown", "50", 990, None),
            ("on", "50", 1010, None),
        ):
            result = template.render(
                states={
                    "wear": SimpleNamespace(state=worn, last_reported=1),
                    "beat": SimpleNamespace(state=heartbeat, last_reported=reported),
                },
                watch_entity="wear",
                heartbeat_entity="beat",
                now=lambda: 1000,
                as_timestamp=lambda value: value,
            )
            self.assertIs(json.loads(result)["worn"], expected)

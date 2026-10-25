from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from okabebot.adapters.media import MEDIA_FACTORIES, MediaSnapshot, create_media_source
from okabebot.adapters.notifications import PollingAdapter
from okabebot.config import load
from okabebot.notifications import Inbox
from okabebot.sources import Sources
from okabebot.cast_music import CastMusic


class AdapterTests(unittest.TestCase):
    def test_factory_and_config_share_extension_registry(self):
        import json

        provider = SimpleNamespace(
            read=lambda: MediaSnapshot(video={"app": "Demo", "title": "Example"})
        )
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(MEDIA_FACTORIES, {"demo": lambda path, settings: provider}),
        ):
            p = Path(folder) / "config.json"
            p.write_text(json.dumps({"spotify": {"source": "demo"}}))
            config = load(p)
            self.assertIs(
                create_media_source(config["spotify"]["source"], Path(folder), config["spotify"]),
                provider,
            )
        with self.assertRaises(ValueError):
            create_media_source("unknown", Path("."), {})

    def test_cast_snapshot_does_not_expose_mutable_callback_state(self):
        source = CastMusic.__new__(CastMusic)
        source.music = {"is_playing": False}
        source.tv = {"app": "TV", "nested": {"title": "Original"}}
        source.settings = {}
        source.connected = True
        source.error = ""
        source.app = "TV"
        result = source.read()
        result.video["nested"]["title"] = "Modified"
        self.assertEqual(source.tv["nested"]["title"], "Original")
        self.assertFalse(result.status["can_authenticate"])

    def test_notification_provider_failure_does_not_block_another_source(self):
        with tempfile.TemporaryDirectory() as folder:
            inbox = Inbox(folder)

            def broken(context):
                raise RuntimeError("private-token-do-not-expose")

            def working(context):
                context.inbox.publish("demo", "Finished", dedupe_key="once")
                context.state["demo_cursor"] = "saved"

            sources = Sources(
                inbox,
                folder,
                {"broken": True, "demo": True},
                adapters=[PollingAdapter("broken", broken), PollingAdapter("demo", working)],
            )
            sources.poll()
            sources.poll()
            self.assertEqual(len(inbox.items()), 1)
            self.assertNotIn("private-token", str(sources.errors))
            self.assertEqual(sources.state["demo_cursor"], "saved")
            self.assertTrue(sources.path.exists())

    def test_authentication_host_policy_is_provider_owned(self):
        from okabebot.adapters.media import begin_auth

        provider = SimpleNamespace(
            status=lambda: {"can_authenticate": True, "auth_hosts": ["accounts.example.org"]},
            begin=lambda: "https://accounts.example.org/authorize",
        )
        self.assertEqual(begin_auth(provider)["allowed_hosts"], ["accounts.example.org"])
        for url in (
            "http://accounts.example.org/authorize",
            "https://other.example.org/authorize",
            "javascript:alert(1)",
        ):
            provider.begin = lambda value=url: value
            with self.assertRaises(ValueError):
                begin_auth(provider)

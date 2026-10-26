"""Webhook-only mode must not invoke GitHub polling adapters."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from okabebot.adapters.notifications import BUILTIN_ADAPTERS
from pi import pip_face, scene


class NotificationModesTests(unittest.TestCase):
    def test_webhook_only_preserves_calendar(self):
        context = SimpleNamespace(
            settings={"github": "all", "calendar": True, "github_polling": False}
        )
        enabled = {adapter.name for adapter in BUILTIN_ADAPTERS if adapter.enabled(context)}
        self.assertEqual({"calendar"}, enabled)
        del context.settings["github_polling"]
        self.assertEqual(3, sum(adapter.enabled(context) for adapter in BUILTIN_ADAPTERS))

    def test_sso_can_consume_only_the_requested_queue(self):
        template = json.loads(Path("infra/aws/queue-sso.json").read_text())
        permissions = template["Resources"]["ConsumerPermission"]["Properties"]
        statement = permissions["InlinePolicy"]["Statement"]
        self.assertEqual(1, len(statement))
        self.assertEqual(
            {"sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"},
            set(statement[0]["Action"]),
        )
        self.assertEqual({"Ref": "QueueArn"}, statement[0]["Resource"])
        self.assertNotIn("ManagedPolicies", permissions)

    def test_pip_leaves_side_lanes_clear(self):
        for kind, coords, _, _ in pip_face.shapes(style="pip")[1:]:
            self.assertGreaterEqual(min(coords[::2]), 125)
            self.assertLessEqual(max(coords[::2]), 355)

    def test_large_media_strip_uses_shared_height(self):
        from pi import layout

        strip, _ = scene.media_title_strip("A video title", None, layout.MEDIA_VIEWPORT)
        self.assertEqual(layout.MEDIA_TITLE_HEIGHT, strip.height)
        self.assertLess(layout.MEDIA_TOP, 273)

    def test_health_restores_character_after_pi_boot(self):
        from unittest.mock import Mock, patch
        from okabebot.bridge import Bridge

        bridge = Bridge.__new__(Bridge)
        bridge.processing = bridge.announcing = False
        bridge.codex = None
        bridge.closing = Mock()
        bridge.closing.is_set.side_effect = [False, True]
        bridge.device_health = {}
        bridge.face_activity = "thinking"
        bridge.face_worker = Mock()
        with (
            patch("okabebot.bridge.device") as device,
            patch("okabebot.bridge.character_tools.speech.health"),
        ):
            device.return_value.rpc.return_value = {"kind": "idle"}
            bridge.poll_health()
        bridge.face_worker.submit.assert_called_once()
        self.assertEqual("thinking", bridge.face_worker.submit.call_args.args[1])

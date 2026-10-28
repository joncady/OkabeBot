import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from okabebot.tv_prepare import TVPreparation


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.worker = TVPreparation(self.tmp.name)
        self.worker.path.write_text(
            json.dumps(
                {
                    "test-tv": {
                        "url": "http://127.0.0.1:8123/api/webhook/invented",
                        "timeout_seconds": 5,
                    }
                }
            )
        )

    def response(self, status):
        worker = self.worker

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            status = 200

        def open_request(request, **kwargs):
            identity = json.loads(request.data)["request_id"]
            self.assertEqual(set(json.loads(request.data)), {"request_id"})
            worker.complete({"request_id": identity, "status": status})
            return Response()

        return open_request

    def test_callback_and_active_input_are_both_required(self):
        with patch("okabebot.tv_prepare.urlopen", side_effect=self.response("input_command_sent")):
            self.assertTrue(self.worker.prepare("test-tv", lambda: True))
        with patch("okabebot.tv_prepare.urlopen", side_effect=self.response("failed")):
            self.assertFalse(self.worker.prepare("test-tv", lambda: True))
        with (
            patch("okabebot.tv_prepare.urlopen", side_effect=self.response("input_command_sent")),
            patch("okabebot.tv_prepare.time.monotonic", side_effect=[0, 13]),
        ):
            self.assertFalse(self.worker.prepare("test-tv", lambda: False))
        self.assertEqual(self.worker.pending, {})

    def test_unknown_replayed_or_malformed_completion_cannot_authorize(self):
        self.assertFalse(
            self.worker.complete({"request_id": "unknown", "status": "input_command_sent"})[
                "accepted"
            ]
        )
        self.worker.pending["invented"] = {"event": threading.Event(), "sent": False}
        self.assertTrue(
            self.worker.complete({"request_id": "invented", "status": "failed"})["accepted"]
        )
        self.assertFalse(
            self.worker.complete({"request_id": "invented", "status": "input_command_sent"})[
                "accepted"
            ]
        )
        self.assertFalse(self.worker.pending["invented"]["sent"])
        with self.assertRaises(ValueError):
            self.worker.complete({"request_id": "invented", "status": "ready", "url": "forbidden"})

    def test_transport_errors_do_not_retry_and_unbound_destination_is_unchanged(self):
        with patch("okabebot.tv_prepare.urlopen", side_effect=OSError) as request:
            self.assertFalse(self.worker.prepare("test-tv", lambda: True))
            request.assert_called_once()
        self.assertTrue(self.worker.prepare("other-tv", lambda: False))

    def test_optional_wake_packet_is_sent_once_before_preparation(self):
        binding = json.loads(self.worker.path.read_text())
        binding["test-tv"]["wake_mac"] = "02:00:00:00:00:01"
        self.worker.path.write_text(json.dumps(binding))
        with patch("okabebot.tv_prepare.socket.socket") as socket_factory:
            with patch(
                "okabebot.tv_prepare.urlopen", side_effect=self.response("input_command_sent")
            ):
                self.assertTrue(self.worker.prepare("test-tv", lambda: True))
            sender = socket_factory.return_value.__enter__.return_value
            packet, target = sender.sendto.call_args.args
            self.assertEqual(packet, b"\xff" * 6 + bytes.fromhex("020000000001") * 16)
            self.assertEqual(target, ("255.255.255.255", 9))
            sender.sendto.assert_called_once()

    def test_shipped_ha_tv_payload_excludes_attributes_and_context_identity(self):
        from pathlib import Path
        import jinja2
        import yaml

        class Loader(yaml.SafeLoader):
            pass

        Loader.add_constructor("!secret", lambda loader, node: "private-placeholder")
        package = yaml.load(
            (Path(__file__).parents[1] / "examples/home-assistant/tv_usage.yaml").read_text(),
            Loader=Loader,
        )
        preparation = yaml.load(
            (
                Path(__file__).parents[1] / "examples/home-assistant/samsung_morning.yaml"
            ).read_text(),
            Loader=Loader,
        )
        self.assertTrue(preparation["automation"][0]["triggers"][0]["local_only"])
        self.assertEqual(preparation["automation"][0]["triggers"][0]["allowed_methods"], ["POST"])
        template = jinja2.Environment()
        template.filters["to_json"] = json.dumps
        payload = template.from_string(package["rest_command"]["okabebot_tv_state"]["payload"])
        value = json.loads(
            payload.render(
                entity_id="media_player.invented_tv",
                state="on",
                event_id="invented-event",
                observed_at=1234,
                attributes={"media_title": "PRIVATE", "volume_level": 1},
            )
        )
        self.assertEqual(set(value), {"entity_id", "state", "event_id", "observed_at"})
        self.assertNotIn("PRIVATE", json.dumps(value))

    def test_unknown_input_requires_explicit_fallback_and_false_still_blocks(self):
        with (
            patch("okabebot.tv_prepare.urlopen", side_effect=self.response("input_command_sent")),
            patch("okabebot.tv_prepare.time.monotonic", side_effect=[0, 0, 13]),
            patch("okabebot.tv_prepare.time.sleep"),
        ):
            self.assertFalse(self.worker.prepare("test-tv", lambda: None))
        data = json.loads(self.worker.path.read_text())
        data["test-tv"]["allow_unknown_input"] = True
        self.worker.path.write_text(json.dumps(data))
        with patch("okabebot.tv_prepare.urlopen", side_effect=self.response("input_command_sent")):
            self.assertTrue(self.worker.prepare("test-tv", lambda: None))
        with (
            patch("okabebot.tv_prepare.urlopen", side_effect=self.response("input_command_sent")),
            patch("okabebot.tv_prepare.time.monotonic", side_effect=[0, 0, 13]),
            patch("okabebot.tv_prepare.time.sleep"),
        ):
            self.assertFalse(self.worker.prepare("test-tv", lambda: False))

    def test_direct_wake_target_precedes_broadcast_without_retries(self):
        binding = json.loads(self.worker.path.read_text())
        binding["test-tv"].update(wake_mac="02:00:00:00:00:01", wake_host="192.0.2.10")
        self.worker.path.write_text(json.dumps(binding))
        with (
            patch("okabebot.tv_prepare.socket.socket") as socket_factory,
            patch("okabebot.tv_prepare.urlopen", side_effect=self.response("input_command_sent")),
        ):
            self.assertTrue(self.worker.prepare("test-tv", lambda: True))
            sender = socket_factory.return_value.__enter__.return_value
            self.assertEqual(
                [call.args[1] for call in sender.sendto.call_args_list],
                [("192.0.2.10", 9), ("255.255.255.255", 9)],
            )

    def test_opt_in_cast_wake_precedes_ha_readiness_and_failure_abstains(self):
        binding = json.loads(self.worker.path.read_text())
        binding["test-tv"]["wake_cast"] = True
        self.worker.path.write_text(json.dumps(binding))
        from unittest.mock import Mock

        wake = Mock(return_value=True)
        with patch("okabebot.tv_prepare.urlopen", side_effect=self.response("input_command_sent")):
            self.assertTrue(self.worker.prepare("test-tv", lambda: True, wake_cast=wake))
        wake.assert_called_once()
        with patch("okabebot.tv_prepare.urlopen") as post:
            self.assertFalse(self.worker.prepare("test-tv", lambda: True, wake_cast=lambda: False))
            self.assertFalse(self.worker.prepare("test-tv", lambda: True))
            post.assert_not_called()

    def test_cast_warmup_has_no_character_token_and_does_not_replace_present_actor(self):
        from unittest.mock import Mock
        from okabebot.bridge import Bridge

        controller = Mock()

        class FakeDashCast:
            def load_url(self, *args, **kwargs):
                controller.load_url(*args, **kwargs)

        bridge = Bridge.__new__(Bridge)
        bridge.surfaces = Mock(phase="pi", active_id="other-tv")
        bridge.port = 8768
        with (
            patch("pychromecast.controllers.dashcast.DashCastController", FakeDashCast),
            patch("okabebot.bridge.get_config", return_value={"web": {"host": "127.0.0.1"}}),
        ):
            self.assertTrue(bridge.wake_destination_cast("test-tv"))
            controller.load_url.assert_called_once_with(
                "http://127.0.0.1:8768/tv/wake/", force=True
            )
            bridge.surfaces.phase, bridge.surfaces.active_id = "tv", "test-tv"
            self.assertTrue(bridge.wake_destination_cast("test-tv"))
            self.assertEqual(controller.load_url.call_count, 1)
            bridge.surfaces.cast_for.return_value = None
            self.assertFalse(bridge.wake_destination_cast("test-tv"))

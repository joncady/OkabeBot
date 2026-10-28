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

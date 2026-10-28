import base64
import json
from unittest.mock import Mock
import unittest

from okabebot.alexa_conversation_consumer import ConversationConsumer
from tests import test_alexa_conversation_relay as fixtures


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ExchangeTests()
        self.fixture.setUp()
        self.request = self.fixture.request
        self.exchange = self.fixture.exchange
        self.exchange.open(self.request)
        self.receiver, self.media, self.infer = Mock(), Mock(), Mock()
        self.receiver.receive_message.return_value = {
            "Messages": [{"Body": json.dumps(self.request), "ReceiptHandle": "private-receipt"}]
        }
        self.infer.return_value = {
            "text": "Air scatters blue light.",
            "audio_safe": True,
            "audio_ready": True,
            "mp3": base64.b64encode(b"ID3" + b"x" * 200).decode(),
            "timings": {"model_s": 0.5},
            "character": "okabe",
            "audio_duration_ms": 2100,
        }
        self.consumer = ConversationConsumer(
            self.exchange,
            self.receiver,
            self.media,
            "private-audio",
            self.request["identity"],
            "private.sock",
            infer=self.infer,
            wall=lambda: self.fixture.now,
        )

    def test_generates_once_and_publishes_only_after_fixed_key_upload(self):
        result = self.consumer.step()
        self.assertEqual(result["state"], "completed")
        self.media.put_object.assert_called_once()
        kwargs = self.media.put_object.call_args.kwargs
        self.assertEqual(kwargs["Key"], "conversation/audio/" + self.request["id"] + ".mp3")
        self.assertEqual(kwargs["ServerSideEncryption"], "AES256")
        self.assertEqual(self.fixture.table.items[self.request["id"]]["status"], "ready")
        reply = self.exchange.wait(self.request, self.fixture.now + 1)
        self.assertEqual((reply["character"], reply["audio_duration_ms"]), ("okabe", 2100))
        self.assertEqual(self.consumer.step()["state"], "ignored")
        self.infer.assert_called_once()
        self.fixture.queue.delete_message.assert_called()

    def test_private_native_answer_never_uploads_even_if_mp3_is_supplied(self):
        self.infer.return_value["audio_safe"] = False
        self.consumer.step()
        self.media.put_object.assert_not_called()
        record = self.fixture.table.items[self.request["id"]]
        self.assertFalse(record["audio_ready"])
        self.assertFalse(record["audio_safe"])

    def test_local_failure_carries_only_allowlisted_stage_and_never_uploads(self):
        self.infer.return_value = {
            "error": "ValueError",
            "stage": "synthesis",
            "message": "private content",
        }
        with self.assertRaises(RuntimeError) as caught:
            self.consumer.step()
        self.assertEqual(caught.exception.alexa_stage, "synthesis")
        self.assertNotIn("private content", str(caught.exception))
        self.media.put_object.assert_not_called()
        self.assertEqual(self.fixture.table.items[self.request["id"]]["status"], "failed")

    def test_unpaired_identity_never_reaches_local_adapter(self):
        self.consumer.identity = "0" * 64
        with self.assertRaises(PermissionError):
            self.consumer.step()
        self.infer.assert_not_called()
        self.media.put_object.assert_not_called()

    def test_expired_inference_cannot_upload_or_publish_ready(self):
        result = self.infer.return_value

        def late(*args):
            self.fixture.advance(7)
            return result

        self.infer.side_effect = late
        with self.assertRaises(TimeoutError):
            self.consumer.step()
        self.media.put_object.assert_not_called()
        self.assertNotEqual(self.fixture.table.items[self.request["id"]]["status"], "ready")

    def test_exit_during_generation_never_uploads_or_publishes_audio(self):
        result = self.infer.return_value

        def cancelled(*args):
            self.exchange.close_session(self.request["session"])
            return result

        self.infer.side_effect = cancelled
        with self.assertRaises(InterruptedError):
            self.consumer.step()
        self.media.put_object.assert_not_called()
        self.assertEqual(self.fixture.table.items[self.request["id"]]["status"], "failed")
        self.assertEqual(self.consumer.step()["state"], "ignored")
        self.infer.assert_called_once()

    def test_upload_failure_is_terminal_and_not_replayed(self):
        self.media.put_object.side_effect = PermissionError("denied")
        with self.assertRaises(PermissionError):
            self.consumer.step()
        self.assertEqual(self.fixture.table.items[self.request["id"]]["status"], "failed")
        self.assertEqual(self.consumer.step()["state"], "ignored")
        self.infer.assert_called_once()

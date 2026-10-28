"""Real exchange over an atomic in-memory DynamoDB boundary; no cloud calls."""

import copy
from decimal import Decimal
from unittest.mock import Mock
import unittest

from okabebot.alexa_conversation import digest
from okabebot.alexa_conversation_relay import ConversationExchange


class ConditionalError(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class Table:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, **kwargs):
        if Item["id"] in self.items:
            raise ConditionalError()
        self.items[Item["id"]] = copy.deepcopy(Item)

    def get_item(self, Key, **kwargs):
        value = self.items.get(Key["id"])
        return {"Item": copy.deepcopy(value)} if value else {}

    def update_item(self, Key, ExpressionAttributeValues, **kwargs):
        item, v = self.items[Key["id"]], ExpressionAttributeValues
        expected = v.get(":queued", v.get(":processing"))
        if item["status"] != expected or item["body_hash"] != v[":hash"]:
            raise ConditionalError()
        if ":now" in v and item["deadline"] <= v[":now"]:
            raise ConditionalError()
        item["status"] = v.get(":terminal", v.get(":ready", "processing"))
        if ":text" in v:
            item.update(text=v[":text"], audio_safe=v[":safe"], audio_ready=v[":audio"])


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.table, self.queue = Table(), Mock()
        self.exchange = ConversationExchange(
            self.table,
            self.queue,
            "private-queue",
            wall=lambda: self.now,
            clock=lambda: self.now,
            sleep=self.advance,
        )
        self.request = {
            "id": "a" * 64,
            "identity": "b" * 64,
            "session": "c" * 64,
            "text": "Why is the sky blue?",
            "body_hash": digest("Why is the sky blue?"),
            "deadline": self.now + 6,
        }

    def advance(self, seconds):
        self.now += seconds

    def test_retry_preserves_deadline_and_deduplicates_before_inference(self):
        self.exchange.open(self.request)
        self.advance(1)
        retry = dict(self.request, deadline=self.now + 6)
        record = self.exchange.open(retry)
        self.assertEqual(record["deadline"], Decimal("1006.0"))
        self.assertNotIn("text", self.table.items[self.request["id"]])
        sends = self.queue.send_message.call_args_list
        self.assertEqual(
            sends[0].kwargs["MessageDeduplicationId"], sends[1].kwargs["MessageDeduplicationId"]
        )
        self.assertTrue(self.exchange.claim(self.request))
        self.assertFalse(self.exchange.claim(self.request))
        conflict = dict(self.request, text="Changed", body_hash=digest("Changed"))
        with self.assertRaises(PermissionError):
            self.exchange.open(conflict)

    def test_completed_reply_is_terminal_and_scoped_to_request(self):
        self.exchange.open(self.request)
        self.assertTrue(self.exchange.claim(self.request))
        answer = {"text": "Air scatters blue light.", "audio_safe": True, "audio_ready": True}
        self.assertTrue(self.exchange.finish(self.request, answer))
        self.assertFalse(self.exchange.finish(self.request, dict(answer, text="Replayed")))
        self.assertFalse(self.exchange.fail(self.request))
        result = self.exchange.wait(self.request, self.now + 6)
        self.assertEqual(result["text"], answer["text"])
        self.assertEqual(result["id"], self.request["id"])
        self.assertFalse(self.exchange.claim(self.request))

    def test_expired_pending_or_running_request_cannot_publish_ready(self):
        self.exchange.open(self.request)
        self.assertTrue(self.exchange.claim(self.request))
        self.advance(7)
        self.assertFalse(self.exchange.claim(self.request))
        self.assertTrue(self.exchange.finish(self.request, {"text": "Late"}))
        self.assertEqual(self.table.items[self.request["id"]]["status"], "expired")
        self.assertIsNone(self.exchange.wait(self.request, self.now + 1))

    def test_wait_has_a_finite_deadline_and_unclaimed_record_stays_unexecuted(self):
        self.exchange.open(self.request)
        self.assertIsNone(self.exchange.wait(self.request, self.now + 2))
        self.assertAlmostEqual(self.now, 1002)
        self.assertEqual(self.table.items[self.request["id"]]["status"], "queued")

    def test_invalid_or_tampered_queue_messages_are_rejected(self):
        self.exchange.open(self.request)
        for invalid in (
            dict(self.request, deadline=1007),
            dict(self.request, text="Different text"),
            dict(self.request, deadline=float("nan")),
            dict(self.request, extra="untrusted"),
        ):
            with self.assertRaises(ValueError):
                self.exchange.claim(invalid)

    def test_access_errors_are_not_treated_as_missing_or_retriable_claims(self):
        self.table.put_item = Mock(side_effect=PermissionError("denied"))
        with self.assertRaises(PermissionError):
            self.exchange.open(self.request)

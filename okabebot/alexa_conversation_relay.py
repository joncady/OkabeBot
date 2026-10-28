"""Dedicated conversation queue/ledger; never the visual destination mailbox.

Injected DynamoDB Table and SQS clients use narrowly scoped IAM credentials.
No prompts are stored in the ledger or logs; queue bodies expire quickly.
"""

from decimal import Decimal
import json
import time

from .alexa_conversation import digest


def conditional_failure(error):
    return (
        getattr(error, "response", {}).get("Error", {}).get("Code")
        == "ConditionalCheckFailedException"
    )


def validate_request(value):
    import math
    import re

    if not isinstance(value, dict) or set(value) != {
        "id",
        "identity",
        "session",
        "text",
        "body_hash",
        "deadline",
    }:
        raise ValueError("Invalid conversation envelope")
    for key in ("id", "identity", "session", "body_hash"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[a-f0-9]{64}", value[key]):
            raise ValueError("Invalid opaque identity")
    if not isinstance(value["text"], str) or not 1 <= len(value["text"].strip()) <= 600:
        raise ValueError("Invalid question")
    if digest(value["text"]) != value["body_hash"]:
        raise ValueError("Question hash mismatch")
    if type(value["deadline"]) not in (float, int) or not math.isfinite(value["deadline"]):
        raise ValueError("Invalid conversation deadline")
    return value


class ConversationExchange:
    def __init__(
        self, table, queue, queue_url, *, wall=time.time, clock=time.monotonic, sleep=time.sleep
    ):
        self.table, self.queue, self.queue_url = table, queue, queue_url
        self.wall, self.clock, self.sleep = wall, clock, sleep

    def get(self, request):
        record = self.table.get_item(Key={"id": request["id"]}, ConsistentRead=True).get("Item")
        if record and any(
            record.get(k) != request[k] for k in ("identity", "session", "body_hash")
        ):
            raise PermissionError("Conversation ledger mismatch")
        return record

    def open(self, request):
        validate_request(request)
        if not 0 < request["deadline"] - self.wall() <= 8:
            raise ValueError("Invalid conversation lifetime")
        record = {k: request[k] for k in ("id", "identity", "session", "body_hash")}
        record.update(
            status="queued",
            deadline=Decimal(str(request["deadline"])),
            expires=int(self.wall()) + 300,
        )
        try:
            self.table.put_item(Item=record, ConditionExpression="attribute_not_exists(id)")
        except Exception as exc:
            if not conditional_failure(exc):
                raise
            record = self.get(request)
            if record is None:
                raise RuntimeError("Conversation ledger disappeared")
        if record["status"] == "queued" and float(record["deadline"]) > self.wall():
            # Safe after an uncertain send: FIFO dedup plus the consumer's atomic
            # claim prevent a repeated inference even across Lambda retries.
            message = dict(request, deadline=float(record["deadline"]))
            self.queue.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message),
                MessageGroupId=request["identity"],
                MessageDeduplicationId=request["id"],
            )
        return record

    def wait(self, request, end):
        while self.clock() < end and self.wall() < request["deadline"]:
            record = self.get(request)
            if record is None:
                raise RuntimeError("Conversation ledger disappeared")
            if record["status"] == "ready":
                return {
                    "id": request["id"],
                    "body_hash": request["body_hash"],
                    "text": record["text"],
                    "audio_safe": record.get("audio_safe") is True,
                    "audio_ready": record.get("audio_ready") is True,
                }
            if record["status"] in ("failed", "expired"):
                return None
            self.sleep(max(0, min(0.12, end - self.clock(), request["deadline"] - self.wall())))
        return None

    def claim(self, request):
        validate_request(request)
        record = self.get(request)
        if record is None or float(record["deadline"]) != request["deadline"]:
            raise ValueError("Request does not match its queued deadline")
        if request["deadline"] <= self.wall():
            return False
        try:
            self.table.update_item(
                Key={"id": request["id"]},
                UpdateExpression="SET #s = :processing",
                ConditionExpression="#s = :queued AND deadline > :now AND body_hash = :hash",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":queued": "queued",
                    ":processing": "processing",
                    ":now": Decimal(str(self.wall())),
                    ":hash": request["body_hash"],
                },
            )
        except Exception as exc:
            if conditional_failure(exc):
                return False
            raise
        return True

    def finish(self, request, result):
        if self.wall() >= request["deadline"]:
            return self.fail(request, "expired")
        text = result.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 600:
            raise ValueError("Invalid generated answer")
        try:
            self.table.update_item(
                Key={"id": request["id"]},
                UpdateExpression="SET #s = :ready, #t = :text, audio_safe = :safe, audio_ready = :audio",
                ConditionExpression="#s = :processing AND deadline > :now AND body_hash = :hash",
                ExpressionAttributeNames={"#s": "status", "#t": "text"},
                ExpressionAttributeValues={
                    ":ready": "ready",
                    ":processing": "processing",
                    ":text": text,
                    ":safe": result.get("audio_safe") is True,
                    ":audio": result.get("audio_ready") is True,
                    ":now": Decimal(str(self.wall())),
                    ":hash": request["body_hash"],
                },
            )
        except Exception as exc:
            if not conditional_failure(exc):
                raise
            return False
        return True

    def fail(self, request, status="failed"):
        if status not in ("failed", "expired"):
            raise ValueError("Invalid terminal state")
        try:
            self.table.update_item(
                Key={"id": request["id"]},
                UpdateExpression="SET #s = :terminal",
                ConditionExpression="#s = :processing AND body_hash = :hash",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":terminal": status,
                    ":processing": "processing",
                    ":hash": request["body_hash"],
                },
            )
        except Exception as exc:
            if not conditional_failure(exc):
                raise
            return False
        return True

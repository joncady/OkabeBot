"""Claim one paired conversational turn; no household actions or physical audio."""

import base64
import json
import time

from .alexa_conversation_relay import bounded_call, validate_request
from .alexa_local import local_request


class ConversationConsumer:
    def __init__(
        self,
        exchange,
        receiver,
        media,
        bucket,
        identity,
        socket_path,
        *,
        infer=local_request,
        wall=time.time,
    ):
        self.exchange, self.receiver, self.media = exchange, receiver, media
        self.bucket, self.identity, self.socket = bucket, identity, socket_path
        self.infer, self.wall = infer, wall

    def step(self):
        messages = self.receiver.receive_message(
            QueueUrl=self.exchange.queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10,
            VisibilityTimeout=10,
        ).get("Messages", [])
        if not messages:
            return {"state": "idle"}
        message = messages[0]
        request, claimed = None, False
        try:
            body = message["Body"]
            if not isinstance(body, str) or len(body.encode()) > 8192:
                raise ValueError("Invalid queued turn")
            request = validate_request(json.loads(body))
            if request["identity"] != self.identity:
                raise PermissionError("Unpaired conversation identity")
            claimed = self.exchange.claim(request)
            if not claimed:
                return {"state": "ignored"}
            started = time.monotonic()
            result = self.infer(self.socket, request)
            if result.get("error"):
                error = RuntimeError("Local conversation unavailable")
                if result.get("stage") in ("model", "synthesis", "encoding"):
                    error.alexa_stage = result["stage"]
                raise error
            if (
                not isinstance(result.get("text"), str)
                or not 1 <= len(result["text"].strip()) <= 600
            ):
                raise ValueError("Invalid local answer")
            if type(result.get("audio_safe")) is not bool:
                raise ValueError("Explicit audio eligibility required")
            if self.exchange.is_closed(request):
                raise InterruptedError("Conversation session ended")
            ready = False
            if result["audio_safe"] and result.get("audio_ready") is True:
                raw = base64.b64decode(result["mp3"], validate=True)
                if not 100 < len(raw) < 2_000_000 or not (
                    raw.startswith(b"ID3") or (raw[0] == 255 and raw[1] & 0xE0 == 0xE0)
                ):
                    raise ValueError("Invalid encoded audio")
                bounded_call(
                    self.media.put_object,
                    request["deadline"],
                    self.wall,
                    Bucket=self.bucket,
                    Key="conversation/audio/" + request["id"] + ".mp3",
                    Body=raw,
                    ContentType="audio/mpeg",
                    CacheControl="private, max-age=120",
                    ServerSideEncryption="AES256",
                )
                ready = True
            completed = self.exchange.finish(
                request,
                {
                    "text": result["text"],
                    "audio_safe": result["audio_safe"],
                    "audio_ready": ready,
                    "character": result.get("character", ""),
                    "audio_duration_ms": result.get("audio_duration_ms", 0),
                },
            )
            return {
                "state": "completed" if completed else "expired",
                "consumer_s": round(time.monotonic() - started, 3),
                "audio_ready": ready,
                "local_timings": result.get("timings", {}),
            }
        except Exception:
            if claimed:
                self.exchange.fail(request)
            raise
        finally:
            # Cleanup has its own short budget. Redelivery still cannot reclaim
            # a processing/terminal request after an uncertain delete.
            bounded_call(
                self.exchange.queue.delete_message,
                self.wall() + 0.6,
                self.wall,
                QueueUrl=self.exchange.queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )

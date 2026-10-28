#!/usr/bin/env python3
"""Run the scoped Alexa conversational consumer. Never plays audio locally."""

import argparse
import fcntl
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument(
        "--lock", type=Path, default=Path(".local/alexa-conversation/consumer.lock")
    )
    args = parser.parse_args()
    value = json.loads(args.deployment.read_text())
    args.lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with args.lock.open("a") as lock:
        args.lock.chmod(0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("A conversational consumer is already running")
        import boto3
        from botocore.config import Config
        from okabebot.alexa_conversation_relay import aws_exchange
        from okabebot.alexa_conversation_consumer import ConversationConsumer

        session = boto3.Session(profile_name=args.profile, region_name=value["region"])
        exchange = aws_exchange(
            session, value["ConversationTableName"], value["ConversationQueueUrl"]
        )
        receiver = session.client(
            "sqs",
            config=Config(connect_timeout=0.3, read_timeout=12, retries={"total_max_attempts": 1}),
        )
        media = session.client(
            "s3",
            config=Config(connect_timeout=0.3, read_timeout=0.5, retries={"total_max_attempts": 1}),
        )
        worker = ConversationConsumer(
            exchange,
            receiver,
            media,
            value["ConversationAudioBucket"],
            value["paired_identity"],
            args.socket,
        )
        try:
            while True:
                try:
                    report = worker.step()
                    if report["state"] != "idle":
                        print(json.dumps(report), flush=True)
                except Exception as exc:
                    report = {"state": "error", "type": type(exc).__name__}
                    if getattr(exc, "alexa_stage", None) in ("model", "synthesis", "encoding"):
                        report["stage"] = exc.alexa_stage
                    print(json.dumps(report), flush=True)
                    time.sleep(1)
        except KeyboardInterrupt:
            print("Conversation consumer stopped. Uncertain turns will not be replayed.")


if __name__ == "__main__":
    main()

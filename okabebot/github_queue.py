"""Outbound-only SQS long polling; acknowledge only after durable local handling."""

import base64
import json
import os
import subprocess
import threading
import time


class AwsQueueClient:
    def __init__(self, settings):
        self.queue = settings["github_queue_url"]
        self.argv = [
            "aws",
            "--region",
            settings["github_queue_region"],
            "--cli-read-timeout",
            "30",
            "--cli-connect-timeout",
            "5",
        ]
        if settings["github_queue_profile"]:
            self.argv += ["--profile", settings["github_queue_profile"]]
        self.process = None
        self.lock = threading.Lock()
        self.stopped = False

    def call(self, *arguments):
        with self.lock:
            if self.stopped:
                raise RuntimeError("Queue consumer stopped")
            process = subprocess.Popen(
                self.argv + ["sqs"] + list(arguments) + ["--output", "json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ, AWS_PAGER=""),
            )
            self.process = process
        try:
            out, _ = process.communicate(timeout=35)
            if process.returncode:
                raise RuntimeError("AWS queue unavailable; check sign-in and permissions")
            return json.loads(out) if out.strip() else {}
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError("Queue request timed out") from None
        finally:
            with self.lock:
                self.process = None

    def receive(self):
        return self.call(
            "receive-message",
            "--queue-url",
            self.queue,
            "--wait-time-seconds",
            "20",
            "--max-number-of-messages",
            "10",
            "--visibility-timeout",
            "120",
        ).get("Messages", [])

    def delete(self, receipt):
        self.call("delete-message", "--queue-url", self.queue, "--receipt-handle", receipt)

    def close(self):
        with self.lock:
            self.stopped = True
            if self.process and self.process.poll() is None:
                self.process.terminate()


class GitHubQueue:
    def __init__(self, webhook, client, on_event=lambda: None):
        self.webhook, self.client, self.on_event = webhook, client, on_event
        self.stopping = threading.Event()
        self.health = {"configured": True, "available": False, "error": "Connecting to AWS queue"}
        self.thread = threading.Thread(target=self.run, daemon=True, name="github-queue")

    def start(self):
        self.thread.start()

    def close(self):
        self.stopping.set()
        self.client.close()

    def deliver(self, message):
        envelope = json.loads(message["Body"])
        if envelope.get("version") != 1 or len(envelope.get("body_base64", "")) > 750_000:
            raise ValueError("Invalid relay envelope")
        raw = base64.b64decode(envelope["body_base64"], validate=True)
        # Reverify on the Mac: SQS access alone never authorizes hardware actions.
        self.webhook.receive(
            {"X-GitHub-Event": envelope["event"], "X-Hub-Signature-256": envelope["signature"]}, raw
        )
        self.client.delete(message["ReceiptHandle"])
        self.on_event()

    def run(self):
        while not self.stopping.is_set():
            try:
                messages = self.client.receive()
                if self.stopping.is_set():
                    return
                failures = False
                for message in messages:
                    if self.stopping.is_set():
                        return
                    try:
                        self.deliver(message)
                    except Exception:
                        failures = True
                self.health = dict(
                    configured=True,
                    available=not failures,
                    checked_at=time.time(),
                    error="A queued delivery failed; it will retry or move to the dead-letter queue"
                    if failures
                    else None,
                )
            except Exception:
                self.health = dict(
                    configured=True,
                    available=False,
                    error="AWS queue unavailable; check AWS sign-in and permissions",
                )
                self.stopping.wait(10)

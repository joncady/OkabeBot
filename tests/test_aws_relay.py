import base64
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from okabebot.github_queue import GitHubQueue
from okabebot.github_webhook import GitHubWebhook
from okabebot.notifications import Inbox

spec = importlib.util.spec_from_file_location(
    "aws_relay", Path(__file__).resolve().parents[1] / "infra/aws/github_relay.py"
)
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class AwsRelayTests(unittest.TestCase):
    def event(self):
        raw = json.dumps(
            dict(
                repository=dict(full_name="owner/repo"),
                action="completed",
                workflow_run=dict(id=72, run_attempt=1, conclusion="failure", name="Test CI"),
            )
        ).encode()
        signature = "sha256=" + hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
        return dict(
            rawPath="/webhooks/github",
            requestContext=dict(http=dict(method="POST")),
            headers={"x-hub-signature-256": signature, "x-github-event": "workflow_run"},
            body=base64.b64encode(raw).decode(),
            isBase64Encoded=True,
        )

    def test_cloud_to_queue_to_durable_inbox_and_duplicate_ack(self):
        client = Mock()
        event = self.event()
        result = relay.handle(event, client, "queue", "secret", {"owner/repo"})
        self.assertEqual(result["statusCode"], 202)
        body = client.send_message.call_args.kwargs["MessageBody"]
        with tempfile.TemporaryDirectory() as folder:
            inbox = Inbox(folder)
            hook = GitHubWebhook(inbox, ["owner/repo"], "secret")
            queue = Mock()
            consumer = GitHubQueue(hook, queue)
            consumer.deliver(dict(Body=body, ReceiptHandle="first"))
            consumer.deliver(dict(Body=body, ReceiptHandle="second"))
            self.assertEqual(queue.delete.call_count, 2)
            self.assertEqual(len(inbox.items()), 1)

    def test_rejects_signature_repo_route_size_and_queue_failure(self):
        client = Mock()
        event = self.event()
        self.assertEqual(
            relay.handle(event, client, "q", "wrong", {"owner/repo"})["statusCode"], 403
        )
        self.assertEqual(
            relay.handle(event, client, "q", "secret", {"other/repo"})["statusCode"], 403
        )
        self.assertEqual(
            relay.handle(dict(event, rawPath="/state"), client, "q", "secret", {"owner/repo"})[
                "statusCode"
            ],
            404,
        )
        self.assertEqual(
            relay.handle(dict(event, body="x" * 750001), client, "q", "secret", {"owner/repo"})[
                "statusCode"
            ],
            413,
        )
        client.send_message.assert_not_called()
        client.send_message.side_effect = OSError("offline")
        self.assertEqual(
            relay.handle(event, client, "q", "secret", {"owner/repo"})["statusCode"], 503
        )

    def test_local_failure_does_not_ack_message(self):
        event = self.event()
        client = Mock()
        relay.handle(event, client, "q", "secret", {"owner/repo"})
        with tempfile.TemporaryDirectory() as folder:
            inbox = Inbox(folder)
            hook = GitHubWebhook(inbox, ["owner/repo"], "secret")
            queue = Mock()
            consumer = GitHubQueue(hook, queue)
            with patch.object(inbox, "publish", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    consumer.deliver(
                        dict(
                            Body=client.send_message.call_args.kwargs["MessageBody"],
                            ReceiptHandle="one",
                        )
                    )
            queue.delete.assert_not_called()

    def test_infra_has_no_server_or_broad_queue_policy_and_hides_secret(self):
        template = json.loads(
            (Path(__file__).resolve().parents[1] / "infra/aws/github-relay.json").read_text()
        )
        self.assertTrue(template["Parameters"]["WebhookSecret"]["NoEcho"])
        resources = template["Resources"]
        self.assertFalse(
            any(
                r["Type"] in ("AWS::EC2::Instance", "AWS::EC2::NatGateway")
                for r in resources.values()
            )
        )
        actions = resources["ReceiverRole"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ][0]["Action"]
        self.assertEqual(actions, "sqs:SendMessage")
        self.assertEqual(resources["Logs"]["Properties"]["RetentionInDays"], 7)

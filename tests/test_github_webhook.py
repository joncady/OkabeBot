import datetime as dt
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from unittest.mock import patch
from okabebot.github_webhook import GitHubWebhook
from okabebot.notifications import Inbox


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.inbox = Inbox(self.tmp.name)
        self.hook = GitHubWebhook(self.inbox, ["owner/repo"], "test secret")

    def send(self, event, payload):
        payload = dict(payload, repository=dict(full_name="owner/repo"))
        raw = json.dumps(payload).encode()
        return self.hook.receive(
            {
                "X-GitHub-Event": event,
                "X-Hub-Signature-256": "sha256="
                + hmac.new(b"test secret", raw, hashlib.sha256).hexdigest(),
            },
            raw,
        )

    def deployment(self, state, seconds=0):
        return dict(
            deployment=dict(node_id="DE_test", environment="production"),
            deployment_status=dict(
                state=state,
                created_at=dt.datetime.fromtimestamp(
                    time.time() + seconds, dt.timezone.utc
                ).isoformat(),
            ),
        )

    def test_signature_replay_and_polling_dedupe(self):
        with self.assertRaises(PermissionError):
            self.hook.receive({}, b"{}")
        payload = dict(
            action="completed",
            workflow_run=dict(id=42, run_attempt=2, conclusion="failure", name="CI"),
        )
        self.send("workflow_run", payload)
        self.assertTrue(self.send("workflow_run", payload)["duplicate"])
        self.inbox.publish("github", "Polled same run", dedupe_key="workflow-42-2")
        self.assertEqual(len(self.inbox.items()), 1)
        self.assertEqual(self.inbox.items()[0]["audio"], "chime")

    def test_deployment_order_completion_and_restart(self):
        self.send("deployment_status", self.deployment("in_progress", -10))
        self.assertEqual(len(self.hook.deployments([])), 1)
        self.send("deployment_status", self.deployment("success", -5))
        self.send("deployment_status", self.deployment("pending", -20))
        restarted = GitHubWebhook(self.inbox, ["owner/repo"], "test secret")
        self.assertEqual(restarted.deployments([dict(id="DE_test")]), [])
        self.assertTrue(any(n["title"].startswith("Deployed") for n in self.inbox.items()))

    def test_allowlist_and_disabled_receiver(self):
        raw = json.dumps(dict(repository=dict(full_name="other/repo"))).encode()
        headers = {
            "X-Hub-Signature-256": "sha256="
            + hmac.new(b"test secret", raw, hashlib.sha256).hexdigest(),
            "X-GitHub-Event": "workflow_run",
        }
        with self.assertRaises(PermissionError):
            self.hook.receive(headers, raw)
        with self.assertRaises(PermissionError):
            GitHubWebhook(self.inbox, [], "").receive(headers, raw)

    def test_failed_publish_can_be_retried(self):
        event = self.deployment("failure", -3)
        with patch.object(self.inbox, "publish", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.send("deployment_status", event)
        self.send("deployment_status", event)
        self.assertEqual(len(self.inbox.items()), 1)

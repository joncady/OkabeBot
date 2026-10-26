import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from okabebot.github_queue import AwsQueueClient, GitHubQueue, QueueSignInRequired


class QueueAuthTests(unittest.TestCase):
    def test_expired_sso_returns_profile_specific_guidance_without_cli_output(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "aws-config"
            config.write_text("[profile queue-only]\nsso_session = personal\n")
            with patch.dict(os.environ, {"AWS_CONFIG_FILE": str(config)}):
                client = AwsQueueClient(
                    dict(
                        github_queue_url="queue",
                        github_queue_region="us-west-2",
                        github_queue_profile="queue-only",
                    )
                )
            process = Mock(returncode=1)
            process.communicate.return_value = ("", "SSO session expired PRIVATE_ACCOUNT_OUTPUT")
            with patch("okabebot.github_queue.subprocess.Popen", return_value=process):
                with self.assertRaises(QueueSignInRequired) as caught:
                    client.receive()
            self.assertEqual("aws sso login --profile queue-only", caught.exception.command)
            self.assertNotIn("PRIVATE", str(caught.exception))

    def test_access_denied_is_not_reported_as_expired_login(self):
        client = AwsQueueClient(
            dict(
                github_queue_url="queue",
                github_queue_region="us-west-2",
                github_queue_profile="queue-only",
            )
        )
        process = Mock(returncode=1)
        process.communicate.return_value = ("", "AccessDenied PRIVATE_ACCOUNT_OUTPUT")
        with patch("okabebot.github_queue.subprocess.Popen", return_value=process):
            with self.assertRaises(RuntimeError) as caught:
                client.receive()
        self.assertNotIsInstance(caught.exception, QueueSignInRequired)
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_consumer_reports_auth_guidance_and_recovers_after_renewal(self):
        client = Mock()
        client.receive.side_effect = [QueueSignInRequired("aws sso login --profile queue-only"), []]
        consumer = GitHubQueue(Mock(), client)
        consumer.stopping = Mock()
        consumer.stopping.is_set.side_effect = [False, False, False, True]
        seen = []
        consumer.stopping.wait.side_effect = lambda _: seen.append(dict(consumer.health))
        consumer.run()
        self.assertTrue(seen[0]["auth_required"])
        self.assertIn("aws sso login", seen[0]["reauth_command"])
        self.assertTrue(consumer.health["available"])
        self.assertNotIn("reauth_command", consumer.health)
        json.dumps(consumer.health)

    def test_assumed_role_guidance_renews_its_source_login(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "aws-config"
            config.write_text(
                "[profile queue-role]\nsource_profile = owner-login\n[profile owner-login]\nlogin_session = personal\n"
            )
            with patch.dict(os.environ, {"AWS_CONFIG_FILE": str(config)}):
                client = AwsQueueClient(
                    dict(
                        github_queue_url="queue",
                        github_queue_region="us-west-2",
                        github_queue_profile="queue-role",
                    )
                )
            self.assertEqual("aws login --profile owner-login", client.login_command)
            self.assertEqual("queue-role", client.argv[client.argv.index("--profile") + 1])

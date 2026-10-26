import tempfile
import unittest
from pathlib import Path
from okabebot.integration_auth import notification_token, may_publish


class IntegrationAuthTests(unittest.TestCase):
    def test_persistent_private_publish_only(self):
        with tempfile.TemporaryDirectory() as folder:
            token = notification_token(folder)
            self.assertEqual(token, notification_token(folder))
            self.assertEqual((Path(folder) / "notification-token").stat().st_mode & 0o777, 0o600)
            hosts = {"localhost:8768"}
            self.assertTrue(may_publish("/notifications", "localhost:8768", hosts, token, token))
            for path in ["/state", "/enabled", "/notifications/dismiss", "/spotify/connect"]:
                self.assertFalse(may_publish(path, "localhost:8768", hosts, token, token))
            self.assertFalse(may_publish("/notifications", "evil", hosts, token, token))
            self.assertFalse(may_publish("/notifications", "localhost:8768", hosts, "wrong", token))

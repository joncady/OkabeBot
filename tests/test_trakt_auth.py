"""Invented OAuth responses; no real credentials or histories."""

import tempfile
import unittest
from okabebot.amadeus_feeds import Feeds
from okabebot.amadeus_onboarding import Onboarding, SYSTEM
from okabebot.amadeus_habits import preference
from okabebot.trakt_auth import TraktAuth
from tests.test_amadeus_http import SETUP


class AuthTests(unittest.TestCase):
    def test_interval_private_tokens_rotation_and_disconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            owner = Onboarding(folder)
            owner.save(SETUP)
            now = [2000000000]
            feeds = Feeds(folder, clock=lambda: now[0])
            calls = []

            def read(url, headers, data):
                calls.append((url, data))
                if url.endswith("device/code"):
                    return dict(
                        device_code="private-code", user_code="ABCD", expires_in=600, interval=5
                    )
                return dict(
                    access_token="private-access", refresh_token="private-refresh", expires_in=600
                )

            auth = TraktAuth(feeds, read)
            feeds.trakt_auth = auth
            public = auth.action(dict(action="start", client_id="invented", client_secret="secret"))
            self.assertNotIn("private-code", str(public))
            self.assertEqual(auth.action({"action": "check"})["state"], "awaiting_approval")
            self.assertEqual(len(calls), 1)
            now[0] += 6
            self.assertTrue(auth.action({"action": "check"})["state"].startswith("authorized"))
            with feeds.store() as store:
                connection = preference(store, SYSTEM, "feed_connection.trakt")
            self.assertNotIn("private-refresh", str(feeds.snapshot()))
            now[0] += 500
            refreshed = auth.refresh(connection)
            self.assertGreater(refreshed["expires_at"], connection["expires_at"])
            auth.action(dict(action="start", client_id="invented", client_secret="secret"))
            feeds.connect({"transport": "trakt", "disconnect": True})
            self.assertIsNone(auth.pending)
            self.assertEqual(auth.action({"action": "check"})["state"], "expired_restart_sign_in")
            owner.close()

    def test_uncertain_single_use_refresh_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            feeds = Feeds(folder, clock=lambda: 2000000000)
            auth = feeds.trakt_auth
            connection = dict(
                client_id="invented",
                client_secret="secret",
                token="access",
                refresh_token="refresh",
                expires_at=1,
            )
            auth.save({}, connection)
            calls = []

            def fail(*args):
                calls.append(True)
                raise TimeoutError("upstream body must not escape")

            auth.read = fail
            with self.assertRaises(ValueError):
                auth.refresh(connection)
            with feeds.store() as store:
                blocked = preference(store, SYSTEM, "feed_connection.trakt")
            with self.assertRaises(ValueError):
                auth.refresh(blocked)
            self.assertEqual(len(calls), 1)

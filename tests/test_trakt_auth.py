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

    def test_new_app_device_flow_omits_unissued_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            owner = Onboarding(folder)
            owner.save(SETUP)
            now = [2000000000]
            feeds = Feeds(folder, clock=lambda: now[0])
            calls = []

            def read(url, headers, data):
                self.assertEqual(headers["trakt-api-key"], "invented")
                self.assertEqual(headers["trakt-api-version"], "2")
                self.assertTrue(headers["User-Agent"].startswith("OkabeBot/"))
                calls.append(data)
                if url.endswith("device/code"):
                    return dict(
                        device_code="private-code", user_code="ABCD", expires_in=600, interval=5
                    )
                self.assertNotIn("client_secret", data)
                return dict(access_token="access", refresh_token="refresh", expires_in=600)

            auth = TraktAuth(feeds, read)
            auth.action(dict(action="start", client_id="invented", client_secret=""))
            now[0] += 6
            auth.action({"action": "check"})
            with feeds.store() as store:
                connection = preference(store, SYSTEM, "feed_connection.trakt")
            now[0] += 500
            auth.refresh(connection)
            self.assertEqual(len(calls), 3)
            owner.close()

    def test_external_refresh_lock_blocks_rotation_without_poisoning_connection(self):
        from unittest.mock import Mock, patch
        from okabebot.trakt_auth import refresh_lock

        with tempfile.TemporaryDirectory() as folder:
            owner = Onboarding(folder)
            self.addCleanup(owner.close)
            owner.save(SETUP)
            feeds = Feeds(folder, clock=lambda: 2000000000)
            connection = {
                "client_id": "invented",
                "token": "old",
                "refresh_token": "once",
                "expires_at": 0,
            }
            owner.store.remember(SYSTEM, "feed_connection.trakt", connection)
            read = Mock(
                return_value={"access_token": "new", "refresh_token": "next", "expires_in": 600}
            )
            auth = TraktAuth(feeds, read)
            # An independently opened lock stands in for a standalone MCP process.
            with refresh_lock(folder):
                with patch(
                    "okabebot.trakt_auth.refresh_lock",
                    side_effect=lambda path: refresh_lock(path, timeout=0),
                ):
                    with self.assertRaises(ValueError):
                        auth.refresh(connection)
                read.assert_not_called()
                self.assertEqual(
                    preference(owner.store, SYSTEM, "feed_connection.trakt"), connection
                )
            self.assertEqual(auth.refresh(connection)["token"], "new")
            read.assert_called_once()

    def test_owner_reauthorization_clears_old_account_records_but_refresh_does_not(self):
        from okabebot.context_records import ingest
        from okabebot.amadeus import Store
        from contextlib import closing

        with tempfile.TemporaryDirectory() as folder:
            owner = Onboarding(folder)
            self.addCleanup(owner.close)
            owner.save(SETUP)
            feeds = Feeds(folder, clock=lambda: 2000000000)
            old = {"client_id": "invented", "token": "old"}
            new = {"client_id": "invented", "token": "rotated"}
            feeds.trakt_auth.save({}, old)
            with feeds.store() as store, store.db:
                ingest(
                    store,
                    "watch_history",
                    SETUP["profile"],
                    [{"id": "invented", "title": "Invented Movie", "type": "movie"}],
                    complete=True,
                    valid_until=2000000600,
                )
            feeds.trakt_auth.save(old, new)
            with feeds.store() as store:
                self.assertEqual(
                    1,
                    store.db.execute(
                        "SELECT count(*) FROM context_records WHERE source='watch_history'"
                    ).fetchone()[0],
                )
            feeds.trakt_auth.save(
                new, {"client_id": "invented", "token": "other-account"}, rebind=True
            )
            with closing(Store(folder)) as store:
                self.assertEqual(
                    0,
                    store.db.execute(
                        "SELECT count(*) FROM context_records WHERE source='watch_history'"
                    ).fetchone()[0],
                )
                self.assertEqual(
                    0,
                    store.db.execute(
                        "SELECT count(*) FROM context_changes WHERE source='watch_history'"
                    ).fetchone()[0],
                )
                self.assertTrue(preference(store, SYSTEM, "feed_connection_revision.trakt"))

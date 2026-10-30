"""Invented on-demand library fixtures; no account data or viewing history."""

import json
import tempfile
import unittest
from unittest.mock import Mock
from okabebot.amadeus_onboarding import Onboarding, SYSTEM
from okabebot.trakt_library import watchlist
from tests.test_amadeus_http import SETUP


class WatchlistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.owner = Onboarding(self.tmp.name)
        self.addCleanup(self.owner.close)
        self.owner.save(dict(SETUP, sources=[]))
        self.owner.control({"paused": False})
        self.owner.store.remember(
            SYSTEM, "feed_connection.trakt", {"client_id": "fake-app", "token": "fake-token"}
        )

    def test_on_demand_read_does_not_enable_collection_or_store_titles(self):
        read = Mock(
            return_value=[
                {
                    "type": "movie",
                    "movie": {"title": "Invented Moon Film", "year": 2001, "ids": {"trakt": 42}},
                }
            ]
        )
        result = watchlist(self.tmp.name, read=read)
        self.assertEqual(result["items"][0]["id"], "42")
        self.assertIn("sync/watchlist/movies?", read.call_args.args[0])
        self.assertNotIn("fake-token", json.dumps(result))
        self.assertEqual(
            self.owner.store.db.execute("SELECT count(*) FROM events").fetchone()[0], 0
        )
        self.assertNotIn("Invented Moon Film", json.dumps(self.owner.export()))

    def test_pause_and_in_flight_revocation_hide_results(self):
        read = Mock(return_value=[])
        self.owner.control({"paused": True})
        self.assertEqual(watchlist(self.tmp.name, read=read)["state"], "paused_or_not_configured")
        read.assert_not_called()
        self.owner.control({"paused": False})

        def revoke(*args):
            self.owner.control({"guest": True})
            return []

        self.assertEqual(watchlist(self.tmp.name, read=revoke)["state"], "context_changed")

    def test_paging_and_bad_parameters(self):
        rows = [
            {"type": "movie", "movie": {"title": "Invented", "ids": {"trakt": n}}}
            for n in range(20)
        ]
        result = watchlist(self.tmp.name, page=2, read=Mock(return_value=rows))
        self.assertEqual(result["next_page"], 3)
        for kw in ({"page": True}, {"page": 0}, {"kind": "../history"}):
            with self.assertRaises(ValueError):
                watchlist(self.tmp.name, **kw)

    def test_auth_wrappers_share_controller_rotation_lock(self):
        from okabebot.amadeus_feeds import Feeds

        first, second = Feeds(self.tmp.name), Feeds(self.tmp.name)
        self.assertIs(first.trakt_auth.lock, second.trakt_auth.lock)

    def test_recommendation_composition_requires_a_returned_title(self):
        from okabebot.tool_reply import acceptable

        result = {"items": [{"title": "Invented Moon Film", "year": 2001, "type": "movie"}]}
        self.assertFalse(acceptable("Try Fake City Pop Movie.", "get_trakt_watchlist", result, ""))
        self.assertTrue(
            acceptable(
                "Try Invented Moon Film from your watchlist.", "get_trakt_watchlist", result, ""
            )
        )

    def test_owned_list_discovery_is_explicit_transient_and_not_observation(self):
        from okabebot.trakt_library import owned_lists
        from okabebot.adapters.context.providers import ProviderPage

        read = Mock(
            return_value=ProviderPage(
                [{"name": "Invented Watched Dates Unknown", "ids": {"trakt": 42}, "item_count": 7}],
                {
                    "X-Pagination-Page": "1",
                    "X-Pagination-Page-Count": "1",
                    "X-Pagination-Limit": "100",
                },
            )
        )
        result = owned_lists(self.tmp.name, read=read)
        self.assertEqual("42", result["items"][0]["id"])
        self.assertTrue(result["complete"])
        self.assertIsNone(result["next_page"])
        self.assertIn("/users/me/lists?", read.call_args.args[0])
        self.assertNotIn("Invented Watched", json.dumps(self.owner.export()))
        self.assertNotIn("watch_history", self.owner.settings()["sources"])
        self.owner.control({"guest": True})
        read.reset_mock()
        self.assertEqual("paused_or_not_configured", owned_lists(self.tmp.name, read=read)["state"])
        read.assert_not_called()

    def test_connection_generation_change_during_refresh_aborts_before_read(self):
        from unittest.mock import patch
        from okabebot.amadeus_feeds import Feeds
        from okabebot.trakt_library import owned_lists

        read = Mock(return_value=[])

        def rebind(connection):
            self.owner.store.remember(SYSTEM, "feed_connection_revision.trakt", "new-binding")
            return connection

        with patch("okabebot.trakt_auth.TraktAuth.refresh", side_effect=rebind):
            self.assertEqual("context_changed", watchlist(self.tmp.name, read=read)["state"])
            self.owner.store.db.execute(
                "DELETE FROM preferences WHERE key='feed_connection_revision.trakt'"
            )
            self.owner.store.db.commit()
            self.assertEqual("context_changed", owned_lists(self.tmp.name, read=read)["state"])
        read.assert_not_called()
        feeds = Feeds(self.tmp.name)
        feeds.connect({"transport": "trakt", "client_id": "invented", "token": "new-token"})
        with feeds.store() as store:
            from okabebot.amadeus_habits import preference

            old = preference(store, SYSTEM, "feed_connection_revision.trakt")
        feeds.connect({"transport": "trakt", "client_id": "invented", "token": ""})
        with feeds.store() as store:
            self.assertEqual(old, preference(store, SYSTEM, "feed_connection_revision.trakt"))
        feeds.connect({"transport": "trakt", "disconnect": True})
        with feeds.store() as store:
            self.assertNotEqual(old, preference(store, SYSTEM, "feed_connection_revision.trakt"))

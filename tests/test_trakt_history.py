"""Invented history/list pages; no participant records, account requests or writes."""

from datetime import datetime, timezone
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from okabebot.adapters.context import FEEDS, validate_config, validate_snapshot
from okabebot.adapters.context.providers import ProviderPage
from okabebot.amadeus_feeds import default
from okabebot.trakt_history import collect, CollectionCancelled, page_result

NOW = 2_000_000_000
AUTH = {"client_id": "invented-app", "token": "invented-token"}


def history(ident, when=NOW - 100):
    return {
        "id": ident,
        "type": "movie",
        "watched_at": datetime.fromtimestamp(when, timezone.utc).isoformat(),
        "movie": {"title": "Invented Moon Film " + str(ident)},
    }


def page(rows, current=1, count=1, limit=100):
    return ProviderPage(
        rows,
        {
            "x-pagination-page": str(current),
            "x-pagination-page-count": str(count),
            "x-pagination-limit": str(limit),
        },
    )


class HistoryTests(unittest.TestCase):
    def config(self, **kwargs):
        return {**default(FEEDS["watch_history"]), "enabled": True, **kwargs}

    def test_requested_limit_is_not_used_to_infer_page_exhaustion(self):
        read = Mock(side_effect=[page([history(1)], 1, 2, 1), page([history(2)], 2, 2, 1)])
        items, complete = collect(self.config(page_budget=2), NOW, AUTH, read=read)
        self.assertTrue(complete)
        self.assertEqual(2, len(items))
        queries = [parse_qs(urlsplit(c.args[0]).query) for c in read.call_args_list]
        self.assertEqual(["2"], queries[1]["page"])
        self.assertEqual(queries[0]["end_at"], queries[1]["end_at"])
        self.assertEqual("trakt_history", items[0]["provenance"])

    def test_global_budget_round_robins_selected_sources_and_marks_partial(self):
        read = Mock(
            side_effect=[
                page([history(1)], 1, 2),
                page(
                    [
                        {
                            "type": "movie",
                            "listed_at": "2040-01-01",
                            "movie": {"ids": {"trakt": 7}, "title": "Invented Unknown-Date Film"},
                        }
                    ],
                    1,
                    2,
                ),
            ]
        )
        items, complete = collect(
            self.config(page_budget=2, watched_lists=["42"]), NOW, AUTH, read=read
        )
        self.assertFalse(complete)
        self.assertEqual(2, read.call_count)
        self.assertIn("users/me/lists/42/items", read.call_args_list[1].args[0])
        unknown = next(i for i in items if i["provenance"] == "owner_selected_trakt_list")
        self.assertEqual("watched_date_unknown", unknown["watch_state"])
        self.assertNotIn("watched_at", unknown)
        validate_snapshot(
            {
                "provider": "watch_history",
                "items": items,
                "complete": "no",
                "valid_until_at": NOW + 60,
            }
        )

    def test_every_endpoint_must_finish_before_union_is_complete(self):
        read = Mock(
            side_effect=[page([history(1)], 1, 2), page([], 1, 1), page([history(2)], 2, 2)]
        )
        items, complete = collect(
            self.config(page_budget=3, watched_lists=["42"]), NOW, AUTH, read=read
        )
        self.assertTrue(complete)
        self.assertEqual(2, len(items))
        self.assertEqual(3, read.call_count)

    def test_partial_endpoint_failure_retains_other_results_without_certifying_deletion(self):
        read = Mock(side_effect=[page([history(1)]), TimeoutError("private provider payload")])
        items, complete = collect(
            self.config(page_budget=2, watched_lists=["42"]), NOW, AUTH, read=read
        )
        self.assertFalse(complete)
        self.assertEqual(1, len(items))
        read = Mock(side_effect=TimeoutError("private provider payload"))
        with self.assertRaisesRegex(ValueError, "unavailable"):
            collect(self.config(), NOW, AUTH, read=read)

    def test_context_change_cancels_before_another_page_and_discards_results(self):
        read = Mock(return_value=page([history(1)], 1, 2))
        gate = Mock(side_effect=[True, False])
        with self.assertRaises(CollectionCancelled):
            collect(self.config(page_budget=2), NOW, AUTH, read=read, allowed=gate)
        self.assertEqual(1, read.call_count)
        read.reset_mock()
        with self.assertRaises(CollectionCancelled):
            collect(self.config(), NOW, AUTH, read=read, allowed=lambda: False)
        read.assert_not_called()

    def test_coverage_is_explicit_window_and_missing_headers_never_mean_complete(self):
        read = Mock(return_value=[history(1), history(2, NOW - 31 * 86400)])
        items, complete = collect(self.config(), NOW, AUTH, read=read)
        self.assertFalse(complete)
        self.assertEqual(1, len(items))
        items, complete = collect(self.config(history_days=60), NOW, AUTH, read=read)
        self.assertFalse(complete)
        self.assertEqual(2, len(items))
        self.assertFalse(collect(self.config(), NOW, AUTH, read=Mock(return_value=[]))[1])

    def test_inconsistent_page_counts_cannot_certify_complete(self):
        read = Mock(
            side_effect=[page([history(1)], 1, 2), page([history(2)], 2, 3), page([], 3, 3)]
        )
        self.assertFalse(collect(self.config(page_budget=3), NOW, AUTH, read=read)[1])
        with self.assertRaises(ValueError):
            page_result(page([], current=2), 1)

    def test_legacy_defaults_do_not_expand_reads_and_new_settings_validate(self):
        cfg = validate_config(FEEDS["watch_history"], {"enabled": True})
        self.assertEqual(1, cfg["page_budget"])
        self.assertEqual(30, cfg["history_days"])
        self.assertEqual([], cfg["watched_lists"])
        for change in (
            {"history_days": True},
            {"page_budget": 21},
            {"watched_lists": ["../history"]},
            {"watched_lists": ["42"]},
            {"watched_lists": ["42", "42"], "page_budget": 3},
        ):
            with self.assertRaises(ValueError):
                validate_config(FEEDS["watch_history"], self.config(**change))


class TraktFeedBoundaryTests(unittest.TestCase):
    def test_narrowed_list_or_window_scope_clears_stored_records(self):
        import tempfile
        from contextlib import closing
        from okabebot.amadeus import Store
        from okabebot.amadeus_feeds import Feeds
        from okabebot.amadeus_onboarding import Onboarding
        from tests.test_amadeus_http import SETUP

        with tempfile.TemporaryDirectory() as directory:
            owner = Onboarding(directory)
            self.addCleanup(owner.close)
            owner.save(dict(SETUP, sources=[]))
            owner.control({"paused": False})
            feeds = Feeds(
                directory,
                clock=lambda: NOW,
                reader=lambda *args: (
                    [
                        {
                            "id": "invented-item",
                            "title": "Invented Movie",
                            "type": "movie",
                            "watch_state": "watched_date_unknown",
                            "provenance": "owner_selected_trakt_list",
                            "list_id": "42",
                        }
                    ],
                    True,
                ),
            )
            cfg = {
                **default(FEEDS["watch_history"]),
                "enabled": True,
                "page_budget": 2,
                "watched_lists": ["42"],
                "history_days": 60,
            }
            feeds.configure({"id": "watch_history", "config": cfg})
            feeds.tick(only="watch_history")
            self.assertEqual(1, len(feeds.retrieve("watch_history")["items"]))
            self.assertIn("60-day", feeds.retrieve("watch_history")["scope"])
            self.assertIn("not lifetime", feeds.retrieve("watch_history")["scope"])
            feeds.configure({"id": "watch_history", "config": {**cfg, "watched_lists": []}})
            self.assertEqual([], feeds.retrieve("watch_history")["items"])
            with closing(Store(directory)) as store:
                self.assertEqual(
                    0,
                    store.db.execute(
                        "SELECT count(*) FROM context_changes WHERE source='watch_history'"
                    ).fetchone()[0],
                )
            feeds.tick(only="watch_history")
            self.assertEqual(1, len(feeds.retrieve("watch_history")["items"]))
            feeds.configure(
                {"id": "watch_history", "config": {**cfg, "watched_lists": [], "history_days": 30}}
            )
            self.assertEqual([], feeds.retrieve("watch_history")["items"])

    def test_owner_pause_or_forget_between_pages_cancels_before_another_network_read(self):
        import tempfile
        from unittest.mock import patch
        from okabebot.amadeus_feeds import Feeds
        from okabebot.amadeus_onboarding import Onboarding
        from tests.test_amadeus_http import SETUP
        from okabebot.trakt_history import collect as real_collect

        for action in ("pause", "forget"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                owner = Onboarding(directory)
                try:
                    owner.save(dict(SETUP, sources=[]))
                    owner.control({"paused": False})
                    feeds = Feeds(directory, clock=lambda: NOW)
                    feeds.connect(
                        {"transport": "trakt", "client_id": "invented", "token": "invented"}
                    )
                    feeds.configure(
                        {
                            "id": "watch_history",
                            "config": {
                                **default(FEEDS["watch_history"]),
                                "enabled": True,
                                "page_budget": 2,
                            },
                        }
                    )

                    def read(*args):
                        if action == "pause":
                            owner.control({"paused": True})
                        else:
                            owner.forget({"confirm": "forget_amadeus"})
                        return page([history(1)], 1, 2)

                    network = Mock(side_effect=read)
                    with patch(
                        "okabebot.trakt_history.collect",
                        side_effect=lambda cfg, now, connection, allowed: real_collect(
                            cfg, now, connection, read=network, allowed=allowed
                        ),
                    ):
                        feeds.tick(only="watch_history")
                    self.assertEqual(1, network.call_count)
                    self.assertEqual("context_changed", feeds.health["watch_history"]["state"])
                    self.assertEqual(
                        0,
                        owner.store.db.execute(
                            "SELECT count(*) FROM events WHERE source='watch_history'"
                        ).fetchone()[0],
                    )
                finally:
                    owner.close()

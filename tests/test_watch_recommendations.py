"""Invented watchlists/metadata only: no account, model, network or real history."""

import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from okabebot.amadeus_onboarding import Onboarding, SYSTEM
from okabebot.watch_recommendations import recommendations, fallback
from okabebot.tool_reply import facts, acceptable, preserve_scope
from tests.test_amadeus_http import SETUP


def movie(ident, title, **metadata):
    return {
        "type": "movie",
        "movie": {"ids": {"trakt": ident}, "title": title, "year": 2001, **metadata},
    }


class RecommendationTests(unittest.TestCase):
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
        self.rows = [
            movie(41, "Invented Slow Orbit", genres=["science-fiction"], runtime=89),
            movie(42, "Invented Big Valley", genres=["drama"], runtime=145),
            movie(43, "Invented Missing Metadata"),
        ]

    def history(self, items):
        self.owner.save(dict(SETUP, sources=["watch_history"]))
        self.owner.control({"paused": False})
        self.owner.store.remember(
            SYSTEM, "feed.watch_history", {"enabled": True, "watched_lists": ["99"]}
        )
        now = self.owner.store.clock()
        self.owner.store.sources = {"watch_history"}
        self.owner.store.observe(
            source="watch_history",
            external_id="invented-cache",
            subject=SETUP["profile"],
            kind="feed_snapshot",
            payload={
                "provider": "watch_history",
                "items": items,
                "complete": "yes",
                "valid_until_at": now + 600,
            },
        )

    def test_metadata_is_explicit_and_partial_constraints_do_not_make_up_values(self):
        read = Mock(return_value=self.rows)
        result = recommendations(self.tmp.name, genre="science fiction", max_minutes=100, read=read)
        self.assertEqual(["41"], [v["id"] for v in result["items"]])
        self.assertEqual(result["unknown_metadata_excluded"], 1)
        self.assertEqual(result["history_coverage"], "unknown")
        self.assertIn("runtime", result["items"][0]["why_fit"][-1])
        self.assertEqual(parse_qs(urlsplit(read.call_args.args[0]).query)["extended"], ["full"])
        self.assertEqual(result["availability"], "not_checked")
        self.assertNotIn("fake-token", str(result))
        read.assert_called_once()
        self.assertNotIn("Invented Slow Orbit", str(self.owner.export()))

    def test_saved_genre_orders_candidates_without_claiming_unobserved_mood(self):
        self.owner.store.remember(
            SETUP["profile"], "context.preferences", {"media": {"genres": ["drama"]}}
        )
        result = recommendations(self.tmp.name, read=Mock(return_value=self.rows))
        self.assertEqual("42", result["items"][0]["id"])
        self.assertIn("saved genre", result["items"][0]["why_fit"][-1])
        self.assertNotIn("mood", str(result["items"]))

    def test_date_unknown_seen_ids_excluded_but_episode_does_not_exclude_whole_show(self):
        self.history(
            [
                {
                    "id": "seen-date-unknown",
                    "type": "movie",
                    "title": "Invented Slow Orbit",
                    "trakt_id": "41",
                    "watch_state": "watched_date_unknown",
                    "provenance": "owner_selected_trakt_list",
                    "list_id": "99",
                },
                {
                    "id": "seen-episode",
                    "type": "episode",
                    "title": "Invented Episode",
                    "trakt_id": "77",
                    "watch_state": "watched",
                    "provenance": "trakt_history",
                    "watched_at": self.owner.store.clock() - 30,
                },
            ]
        )
        rows = self.rows + [
            {"type": "show", "show": {"title": "Invented Series", "ids": {"trakt": 77}}}
        ]
        result = recommendations(self.tmp.name, kind="all", read=Mock(return_value=rows))
        self.assertEqual(result["known_watched_excluded"], 1)
        self.assertNotIn("41", [v["id"] for v in result["items"]])
        self.assertIn("77", [v["id"] for v in result["items"]])
        self.assertEqual(result["history_coverage"], "selected_cached_scope")
        self.owner.store.remember(SYSTEM, "feed.watch_history", {"enabled": False})
        result = recommendations(self.tmp.name, read=Mock(return_value=self.rows))
        self.assertEqual(result["known_watched_excluded"], 0)
        self.assertEqual(result["history_coverage"], "unknown")

    def test_unavailable_and_no_verified_match_are_not_invented_recommendations(self):
        self.owner.control({"paused": True})
        read = Mock()
        result = recommendations(self.tmp.name, read=read)
        read.assert_not_called()
        self.assertIn("couldn't read", fallback(result))
        self.owner.control({"paused": False})
        result = recommendations(self.tmp.name, genre="comedy", read=Mock(return_value=self.rows))
        self.assertEqual(result["items"], [])
        self.assertIn("this watchlist page", fallback(result))
        self.assertNotIn("Invented Slow Orbit", fallback(result))

    def test_recommendation_evidence_and_composition_are_candidate_grounded(self):
        result = recommendations(
            self.tmp.name, genre="science-fiction", read=Mock(return_value=self.rows)
        )
        projected = facts("get_watch_recommendations", result, "")
        self.assertIn("why_fit", projected["records"][0])
        self.assertNotIn("id", projected["records"][0])
        good = "I'd pick Invented Slow Orbit: its science-fiction genre matches your request."
        self.assertTrue(acceptable(good, "get_watch_recommendations", result, ""))
        self.assertEqual(preserve_scope(good, "get_watch_recommendations", result), good)
        for text in (
            'Try "Fabricated Other Title" rather than Invented Slow Orbit.',
            "Try Invented Slow Orbit on Netflix.",
            "Try Invented Slow Orbit; you have never watched it.",
            "Try Invented Slow Orbit, a 73-minute film.",
        ):
            with self.subTest(text=text):
                self.assertFalse(acceptable(text, "get_watch_recommendations", result, ""))

    def test_history_consent_change_during_projection_withholds_results(self):
        self.history([])
        from okabebot.amadeus_feeds import context

        def revoke(store, **kwargs):
            value = context(store, **kwargs)
            self.owner.store.remember(SYSTEM, "feed.watch_history", {"enabled": False})
            return value

        with patch("okabebot.watch_recommendations.context", side_effect=revoke):
            result = recommendations(self.tmp.name, read=Mock(return_value=self.rows))
        self.assertEqual(result["state"], "context_changed")

    def test_validation_rejects_unbounded_or_ambiguous_constraints(self):
        for args in (
            {"genre": True},
            {"genre": "x" * 51},
            {"max_minutes": True},
            {"max_minutes": 0},
            {"max_minutes": 601},
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                recommendations(self.tmp.name, **args)

    def test_proactive_explanation_uses_recorded_reason_without_invented_motive(self):
        data = {
            "available": True,
            "suggestion": {
                "id": "opaque-private-id",
                "kind": "checkin",
                "at": 123,
                "reason": "It was an eligible quiet check-in window, and this was an older saved interest.",
                "topic": "interests",
                "feedback": None,
            },
        }
        projected = facts("get_proactive_explanation", data, "")
        self.assertNotIn("opaque-private-id", str(projected))
        self.assertNotIn("at", projected)
        result = preserve_scope(
            "You looked lonely, so I checked in.", "get_proactive_explanation", data
        )
        self.assertEqual(result, data["suggestion"]["reason"])
        self.assertIn(
            "shouldn't guess",
            preserve_scope(
                "I sensed you were bored.", "get_proactive_explanation", {"available": False}
            ),
        )

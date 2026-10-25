import tempfile
import unittest
from unittest.mock import patch
from okabebot.team_resolver import TeamResolver


class ResolverTests(unittest.TestCase):
    def resolver(self, folder):
        def fetch(url, raw=False):
            if "list=search" in url:
                return {"query": {"search": [{"title": "Arsenal F.C."}]}}
            if "/page/summary/" in url:
                return {"title": "Arsenal F.C.", "wikibase_item": "Q9617", "type": "standard"}
            if "EntityData/" in url:
                return {
                    "entities": {
                        "Q9617": {
                            "claims": {
                                "P641": [{"mainsnak": {"datavalue": {"value": {"id": "Q2736"}}}}],
                                "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q476028"}}}}],
                            }
                        }
                    }
                }
            if "wbgetentities" in url:
                return {
                    "entities": {
                        "Q2736": {"labels": {"en": {"value": "association football"}}},
                        "Q476028": {"labels": {"en": {"value": "association football club"}}},
                    }
                }
            raise AssertionError(url)

        return TeamResolver(folder, fetch=fetch)

    def test_dynamic_team_and_disk_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            r = self.resolver(folder)
            try:
                team = r.resolve("Arsenal", "soccer")
                self.assertEqual(team["qid"], "Q9617")
                self.assertEqual(team["sport"], "soccer")
                self.assertEqual(team["key"], "wiki_q9617")
                r.fetch = lambda *a, **k: self.fail("Cache miss")
                self.assertEqual(r.resolve("Arsenal", "soccer"), team)
                self.assertEqual(r.resolve("Arsenal", None), team)
            finally:
                r.close()

    def test_wrong_sport_and_city_abstain(self):
        with tempfile.TemporaryDirectory() as folder:
            r = self.resolver(folder)
            try:
                self.assertIsNone(r.candidate("Arsenal", "Arsenal F.C.", "basketball"))
                fetch = r.fetch
                r.fetch = lambda url, **k: (
                    {"title": "Arsenal", "type": "disambiguation"}
                    if "/summary/" in url
                    else fetch(url, **k)
                )
                self.assertIsNone(r.candidate("Arsenal", "Arsenal", None))
            finally:
                r.close()

    def test_enrichment_is_pure_and_failure_backoff(self):
        with tempfile.TemporaryDirectory() as folder:
            r = self.resolver(folder)
            try:
                v = dict(app="fuboTV", title="Arsenal vs Chelsea", state="BUFFERING")
                a = dict(
                    key="wiki_q1",
                    qid="Q1",
                    name="Arsenal F.C.",
                    aliases=["Arsenal"],
                    sport="soccer",
                    colors=["#ffffff", "#000000"],
                    short_name="ARS",
                    source="https://en.wikipedia.org/wiki/Arsenal_F.C.",
                )
                b = dict(
                    a,
                    key="wiki_q2",
                    qid="Q2",
                    name="Chelsea F.C.",
                    aliases=["Chelsea"],
                    short_name="CHE",
                )
                with patch.object(r, "resolve", side_effect=[a, b]):
                    result = r._enrich(v)
                    self.assertEqual(result["context"]["format"], "sports_live")
                    self.assertEqual(result["context"]["sport"], "soccer")
                    self.assertEqual(len(result["context"]["participants"]), 2)
                with patch.object(r, "_enrich", side_effect=OSError()):
                    r._run("key", v)
                self.assertIn("retry_at", r.results["key"])
            finally:
                r.close()

    def test_ambiguous_candidates_abstain_instead_of_first_search_hit(self):
        from okabebot.team_resolver import team_tokens

        self.assertNotEqual(team_tokens("Manchester"), team_tokens("Manchester United"))
        with tempfile.TemporaryDirectory() as folder:
            resolver = TeamResolver(
                folder, fetch=lambda url: {"query": {"search": [{"title": "A"}, {"title": "B"}]}}
            )
            try:
                with patch.object(
                    resolver,
                    "candidate",
                    side_effect=[{"qid": "Q1", "score": 1}, {"qid": "Q2", "score": 1}],
                ):
                    self.assertIsNone(resolver.resolve("Manchester", "soccer"))
            finally:
                resolver.close()

    def test_provider_failure_preserves_matchup_and_does_not_negative_cache(self):
        from urllib.error import HTTPError

        title = "New York Red Bulls vs. Inter Miami CF | Full Match Highlights"
        with tempfile.TemporaryDirectory() as folder:
            resolver = TeamResolver(
                folder, fetch=lambda url: {"query": {"search": [{"title": "candidate"}]}}
            )
            try:
                with patch.object(resolver, "candidate", side_effect=OSError("temporary")):
                    with self.assertRaises(OSError):
                        resolver.resolve("New York Red Bulls")
                with resolver.db() as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM teams").fetchone()[0], 0)
                with patch.object(
                    resolver,
                    "_enrich",
                    side_effect=HTTPError("https://en.wikipedia.org", 429, "Limited", {}, None),
                ):
                    resolver._run("example", dict(app="YouTube", title=title))
                cached = resolver.results["example"]
                self.assertEqual(len(cached["context"]["participants"]), 2)
                self.assertIn("rate limited", cached["lookup_error"])
                self.assertIn("retry_at", cached)
            finally:
                resolver.close()

    def test_unqualified_club_does_not_select_reserve_squad(self):
        with tempfile.TemporaryDirectory() as folder:
            resolver = self.resolver(folder)
            original = resolver.fetch
            resolver.fetch = lambda url, **kw: (
                {"title": "Arsenal II", "wikibase_item": "Q9617", "type": "standard"}
                if "/summary/" in url
                else original(url, **kw)
            )
            try:
                self.assertIsNone(resolver.candidate("Arsenal", "Arsenal II", None))
            finally:
                resolver.close()

    def test_league_membership_disambiguates_same_city_named_clubs(self):
        def fetch(url, raw=False):
            if "list=search" in url:
                return {"query": {"search": [{"title": "Valencia CF"}, {"title": "Club Valencia"}]}}
            if "/summary/" in url:
                other = "Club_Valencia" in url
                return {
                    "title": "Club Valencia" if other else "Valencia CF",
                    "wikibase_item": "Q20" if other else "Q10",
                    "type": "standard",
                }
            if "EntityData/" in url:
                qid = "Q20" if "Q20" in url else "Q10"
                claims = {
                    p: [{"mainsnak": {"datavalue": {"value": {"id": v}}}}]
                    for p, v in {
                        "P641": "Q2736",
                        "P31": "Q476028",
                        "P118": "Q22" if qid == "Q20" else "Q11",
                    }.items()
                }
                return {"entities": {qid: {"claims": claims}}}
            if "wbgetentities" in url:
                labels = {
                    "Q2736": "association football",
                    "Q476028": "association football club",
                    "Q11": "La Liga",
                    "Q22": "Dhivehi Premier League",
                }
                return {
                    "entities": {k: {"labels": {"en": {"value": v}}} for k, v in labels.items()}
                }
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as folder:
            resolver = TeamResolver(folder, fetch=fetch)
            try:
                self.assertIsNone(resolver.resolve("Valencia", "soccer"))
                resolved = resolver.resolve("Valencia", "soccer", "laliga")
                self.assertEqual(resolved["name"], "Valencia CF")
                self.assertEqual(resolved["league"], "laliga")
                self.assertIsNone(resolver.resolve("Valencia", "soccer"))
            finally:
                resolver.close()

    def test_compressed_svg_name_and_asset_retry_survive_identity_cache(self):
        import io
        from PIL import Image

        hint = TeamResolver.crest_hint(
            {
                "thumbnail": {
                    "source": "https://thumb.wikimedia.org/wikipedia/en/thumb/a/ab/Valenciacf.svg/64px-Valenciacf.svg.png"
                }
            }
        )
        self.assertTrue(hint)
        team = dict(qid="Q10", name="Valencia CF", asset_hint=hint)
        png = io.BytesIO()
        Image.new("RGBA", (16, 16), "orange").save(png, format="PNG")
        calls = []

        def fetch(url, raw=False):
            calls.append(url)
            if raw:
                return png.getvalue()
            return {"query": {"pages": {}}}

        with tempfile.TemporaryDirectory() as folder:
            resolver = TeamResolver(folder, fetch=fetch)
            try:
                with (
                    patch.object(resolver, "fetch", side_effect=OSError("temporary")),
                    patch("okabebot.team_resolver.time.time", return_value=100),
                ):
                    result, expiry, error = resolver.ensure_crest(team)
                    self.assertFalse(result.get("png_base64"))
                    self.assertIn("retrying", error)
                with patch("okabebot.team_resolver.time.time", return_value=expiry + 1):
                    result, expiry, error = resolver.ensure_crest(team)
                    self.assertTrue(result.get("png_base64"))
                    self.assertIsNone(error)
                other = TeamResolver(
                    folder, fetch=lambda *a, **k: self.fail("Persisted asset cache missed")
                )
                try:
                    with patch("okabebot.team_resolver.time.time", return_value=expiry - 1):
                        self.assertTrue(other.ensure_crest(team)[0].get("png_base64"))
                finally:
                    other.close()
            finally:
                resolver.close()

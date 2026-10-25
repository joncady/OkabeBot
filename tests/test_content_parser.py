import unittest
from okabebot.content_parser import parse_video
from okabebot.content import ContentContext
import tempfile


def video(title, **extra):
    return dict(app="YouTube", content_id="example", title=title, **extra)


class ParserTests(unittest.TestCase):
    def test_current_highlight_and_order(self):
        result = parse_video(
            video("Sunderland v. Leeds United | PREMIER LEAGUE HIGHLIGHTS | 10/25/2026")
        )
        c = result["context"]
        self.assertEqual((c["format"], c["sport"]), ("sports_highlights", "soccer"))
        self.assertEqual([p["crest"] for p in c["participants"]], ["sunderland", "leeds_united"])
        self.assertNotIn("score", str(c))
        reverse = parse_video(video("Leeds United vs Sunderland | Premier League Highlights"))
        self.assertEqual(reverse["context"]["participants"][0]["crest"], "leeds_united")

    def test_aliases_and_format(self):
        cases = [
            ("Real Madrid vs FC Barcelona | La Liga highlights", "sports_highlights", "soccer"),
            ("Bournemouth vs AC Milan | UEFA tactical breakdown", "sports_analysis", "soccer"),
            ("NFL Week 8 highlights", "sports_highlights", "american_football"),
            ("NBA highlights", "sports_highlights", "basketball"),
            ("La Liga live coverage", "sports_live", "soccer"),
        ]
        for title, fmt, sport in cases:
            with self.subTest(title=title):
                c = parse_video(video(title))["context"]
                self.assertEqual((c["format"], c["sport"]), (fmt, sport))

    def test_unknown_ambiguous_and_games(self):
        for title in ["My holiday highlights", "Football highlights", "NFL NBA highlights"]:
            self.assertEqual(parse_video(video(title))["context"], {})
        c = parse_video(video("Unknown City vs Another FC | Premier League Highlights"))["context"]
        self.assertEqual(len(c["participants"]), 2)
        self.assertTrue(all(not p["crest"] for p in c["participants"]))
        c = parse_video(video("Bournemouth vs Inter Milan | UEFA highlights"))["context"]
        self.assertEqual(len(c["participants"]), 2)
        self.assertTrue(all(not p["crest"] for p in c["participants"]))
        c = parse_video(video("Real Madrid vs Barcelona | EA FC 26 highlights"))["context"]
        self.assertEqual(c["format"], "gameplay")
        self.assertNotIn("participants", c)
        self.assertEqual(
            parse_video(dict(app="fuboTV", title="NBA highlights"))["context"]["sport"],
            "basketball",
        )

    def test_automatic_plan_and_manual_override(self):
        v = video("Sunderland vs Leeds United | Premier League Highlights")
        with tempfile.TemporaryDirectory() as folder:
            store = ContentContext(folder)
            self.assertEqual(store.get(v)["sport"], "soccer")
            store.set("YouTube", "example", {"format": "comedy_sketch"})
            self.assertEqual(store.get(v)["reaction"], "amused")

    def test_fubo_matchup_defaults_to_live_while_buffering(self):
        result = parse_video(
            dict(
                app="fuboTV Live Production", title="FC Barcelona vs Real Madrid", state="BUFFERING"
            )
        )
        self.assertEqual(result["context"]["format"], "sports_live")
        self.assertEqual(result["context"]["sport"], "soccer")
        self.assertEqual(parse_video(dict(app="fuboTV", title="Evening news"))["context"], {})

    def test_unfamiliar_matchup_keeps_labels_without_sport_or_manual_team_list(self):
        from okabebot.content import plan

        title = "New York Red Bulls vs. Inter Miami CF | Full Match Highlights | Messi in New York!"
        for app in ("YouTube", "Prime Video", "A future streaming app"):
            with self.subTest(app=app):
                result = parse_video(dict(app=app, title=title))
                c = result["context"]
                self.assertEqual(c["format"], "sports_highlights")
                self.assertEqual(c["sport"], "unknown")
                self.assertEqual(
                    [p["name"] for p in c["participants"]], ["New York Red Bulls", "Inter Miami CF"]
                )
                self.assertTrue(all(not p["crest"] for p in c["participants"]))
                self.assertEqual(len(plan(c)["participants"]), 2)
                self.assertNotEqual(plan(c)["prop"], "ball")

    def test_non_sports_versus_titles_do_not_become_matchups(self):
        for title in (
            "Godzilla vs Kong | Movie highlights",
            "Alice vs Bob | Debate highlights",
            "Real Madrid vs Barcelona | FIFA 26 highlights",
        ):
            result = parse_video(video(title))
            self.assertFalse(result["context"].get("participants"))
        self.assertEqual(
            parse_video(video("FIFA World Cup highlights"))["context"]["format"],
            "sports_highlights",
        )

    def test_league_context_is_carried_to_reaction_plan(self):
        from okabebot.content import plan

        context = parse_video(video("Valencia vs. Villarreal | LALIGA Highlights | ESPN FC"))[
            "context"
        ]
        self.assertEqual(context["league"], "laliga")
        self.assertEqual(context["sport"], "soccer")
        self.assertEqual(plan(context)["league"], "laliga")

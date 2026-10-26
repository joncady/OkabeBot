"""Representative synthetic titles, not a measured real-world accuracy dataset."""

import unittest
from okabebot.content_parser import parse_video
from okabebot.content import plan, PRESETS
from pi import scene

SPORTS = [
    ("soccer", "Arsenal vs Chelsea | Premier League Highlights"),
    ("american_football", "Chiefs vs Bills | NFL Full Game Highlights"),
    ("basketball", "Lakers vs Warriors | NBA highlights"),
    ("basketball", "Liberty vs Aces | WNBA recap"),
    ("baseball", "Yankees at Dodgers | MLB recap"),
    ("hockey", "Maple Leafs @ Canadiens | NHL highlights"),
    ("rugby", "Ireland vs France | Rugby highlights"),
    ("cricket", "India vs Australia | Cricket highlights"),
    ("tennis", "Alcaraz vs Sinner | ATP highlights"),
    ("golf", "PGA Tour highlights"),
    ("motorsport", "F1 Race highlights"),
    ("combat", "Fighter One vs Fighter Two | UFC highlights"),
]
FORMATS = {
    "science": "Physics explained",
    "nonprofit": "Charity fundraiser",
    "shorts": "A quick moment #shorts",
    "game_review": "A new game review",
    "film_review": "My movie review",
    "technology_review": "Laptop review: does it last?",
    "trailer": "Official trailer",
    "standup": "Stand-up comedy special",
    "comedy_sketch": "A comedy skit",
    "esports": "Esports championship",
    "gameplay": "Gameplay walkthrough",
    "music_video": "Official music video",
    "concert": "Full concert",
    "podcast": "Science podcast",
    "interview": "Interview with a scientist",
    "news": "Breaking news",
    "asmr": "ASMR rain",
    "relaxation": "Guided meditation",
    "fitness": "Morning workout",
    "food": "Bread recipe",
    "diy": "DIY home repair",
    "automotive": "Electric car review",
    "fashion": "Fashion show",
    "nature": "Wildlife documentary",
    "animals": "Animal rescue",
    "travel": "Travel guide to London",
    "vlog": "Daily vlog",
    "lecture": "Physics lecture",
    "tutorial": "How to fix a lamp",
    "reaction": "A reaction video",
}


class ContentCoverageTests(unittest.TestCase):
    def test_sports_formats_apps_and_no_invented_crests(self):
        for sport, title in SPORTS:
            for app in ("YouTube", "Fubo", "Prime Video", "Future receiver"):
                with self.subTest(sport=sport, app=app):
                    c = parse_video(dict(app=app, title=title), teams=[])["context"]
                    self.assertEqual(c["sport"], sport)
                    self.assertEqual(c["format"], "sports_highlights")
                    self.assertEqual(plan(c)["reaction"], "competitive")
                    self.assertTrue(all(not t["crest"] for t in c["participants"]))

    def test_formats_map_to_existing_art_without_sports_labels(self):
        for fmt, title in FORMATS.items():
            with self.subTest(fmt=fmt):
                c = parse_video(dict(app="YouTube", title=title))["context"]
                self.assertEqual(c["format"], fmt)
                self.assertEqual(plan(c)["preset"], "video." + fmt)
                self.assertFalse(c.get("participants"))

    def test_provider_genres_are_not_movie_name_keyword_guesses(self):
        c = parse_video(
            dict(
                app="Any app",
                title="Unfamiliar title",
                metadata=dict(kind="movie", genres=["Science Fiction", "Mystery"]),
            )
        )["context"]
        self.assertEqual(c["genres"], ["science_fiction", "mystery"])
        self.assertEqual(plan(c)["reaction"], "curious")
        for title in (
            "Love Actually",
            "War of the Worlds",
            "My holiday highlights",
            "Football highlights",
            "NFL NBA highlights",
            "Alice vs Bob debate highlights",
            "Godzilla vs Kong movie highlights",
        ):
            self.assertFalse(
                parse_video(dict(app="YouTube", title=title))["context"].get("participants")
            )

    def test_games_and_unrelated_analysis_are_not_sport(self):
        for title in (
            "Chiefs vs Bills | Madden gameplay",
            "Lakers vs Warriors | NBA 2K highlights",
            "Arsenal vs Chelsea | EA FC highlights",
        ):
            c = parse_video(dict(app="YouTube", title=title))["context"]
            self.assertEqual(c["format"], "gameplay")
            self.assertFalse(c.get("participants"))

    def test_participant_order_suffixes_and_scores(self):
        c = parse_video(
            dict(app="YouTube", title="A Team 2-1 vs B Team 1 | Soccer Full Game Highlights"),
            teams=[],
        )["context"]
        self.assertEqual([p["name"] for p in c["participants"]], ["A Team", "B Team"])

    def test_all_movie_genres_and_sports_render_across_characters(self):
        contexts = [
            dict(kind="movie", genres=[p["id"].split(".")[1]], confidence=0.95)
            for p in PRESETS
            if p["kind"] == "movie"
        ]
        contexts += [
            parse_video(dict(app="YouTube", title=title), teams=[])["context"]
            for _, title in SPORTS
        ]
        for context in contexts:
            for style in ("okabe", "kurisu", "sonic", "pip"):
                with self.subTest(context=context, style=style):
                    reaction = plan(context)
                    image = scene.render(
                        style=style,
                        phase=1,
                        music={
                            "video": dict(
                                state="PLAYING",
                                title="Coverage fixture",
                                app="YouTube",
                                reaction=reaction,
                            )
                        },
                    )
                    self.assertEqual(image.size, (480, 320))
                    self.assertNotEqual(image.getpixel((240, 90)), image.getpixel((0, 90)))

    def test_esports_and_gameplay_take_precedence_over_real_sports_words(self):
        for title, expected in [
            ("Team Liquid vs G2 | Esports highlights", "esports"),
            ("F1 racing gameplay highlights", "gameplay"),
            ("NFL player interview", "interview"),
        ]:
            context = parse_video(dict(app="YouTube", title=title))["context"]
            self.assertEqual(context["format"], expected)
            self.assertFalse(context.get("participants"))

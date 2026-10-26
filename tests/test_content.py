import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from okabebot.content import ContentContext, ContentPreview, PRESETS, SPORTS, plan
from pi import scene, reactions


class ContentTests(unittest.TestCase):
    def test_catalog_playback_and_profiles(self):
        for case in json.loads(Path("examples/content/cases.json").read_text()):
            p = plan(case["context"])
            self.assertIn(p["reaction"], reactions.EMOTIONS)
            for style in ("okabe", "kurisu", "sonic", "pip"):
                video = dict(state=case["state"], reaction=p, app="YouTube", title=case["name"])
                self.assertEqual(
                    scene.render(style=style, music={"video": video}, phase=2).size, (480, 320)
                )
        self.assertEqual(len(PRESETS), 53)

    def test_context_is_scoped_and_low_confidence_is_neutral(self):
        with tempfile.TemporaryDirectory() as folder:
            c = ContentContext(folder)
            c.set("YouTube", "one", {"format": "sports_highlights", "sport": "soccer"})
            self.assertEqual(c.get({"app": "YouTube", "content_id": "one"})["sport"], "soccer")
            self.assertEqual(c.get({"app": "YouTube", "content_id": "two"})["sport"], "unknown")
            with patch("okabebot.content.time.time", return_value=time.time() + 14401):
                self.assertEqual(c.get({"app": "YouTube", "content_id": "one"})["sport"], "unknown")
        self.assertEqual(
            plan({"format": "comedy_sketch", "confidence": 0.2})["reaction"], "attentive"
        )
        with self.assertRaises(ValueError):
            plan({"participants": [{"name": "A", "crest": "../../oops"}]})

    def test_sports_and_priority_yield(self):
        for sport in SPORTS:
            p = plan(
                {
                    "format": "sports_highlights",
                    "sport": sport,
                    "participants": [
                        {"name": "Home", "short_name": "HOM"},
                        {"name": "Away", "short_name": "AWY"},
                    ],
                }
            )
            self.assertTrue(reactions.decorations(p, 1, "PLAYING"))
        for activity in ("speaking", "thinking", "listening"):
            self.assertFalse(reactions.active({"video": {"state": "PLAYING"}}, activity=activity))
        self.assertFalse(
            reactions.active({"video": {"state": "PLAYING"}}, notification={"title": "Hi"})
        )

    def test_progress_survives_silence_and_uses_monotonic_clock(self):
        video = dict(
            title="Video",
            app="YouTube",
            duration=1000,
            position=100,
            state="PLAYING",
            position_received_at=100,
            updated_at=-999999,
        )
        with patch("pi.scene.time.monotonic", return_value=300):
            image = scene.music_card({"video": video})
            self.assertEqual(image.getpixel((140, 314))[:3], (240, 68, 68))
            video["state"] = "PAUSED"
            image = scene.music_card({"video": video})
            self.assertNotEqual(image.getpixel((140, 314))[:3], (240, 68, 68))

    def test_standalone_preview_needs_no_tv_identity(self):
        preview = ContentPreview()
        with patch("okabebot.content.time.monotonic", return_value=100):
            result = preview.start({"format": "sports_live", "sport": "soccer"})
            self.assertTrue(result["preview"])
            self.assertEqual(preview.music()["video"]["reaction"]["sport"], "soccer")
            self.assertNotIn("content_id", preview.music()["video"])
        with patch("okabebot.content.time.monotonic", return_value=191):
            self.assertIsNone(preview.music())
        preview.start({"kind": "movie", "genres": ["comedy"]})
        preview.stop()
        self.assertIsNone(preview.music())

    def test_crest_asset_and_fallback(self):
        known = reactions.badge("real_madrid", "RMA", ("#eeeeee", "#ffffff"))
        fallback = reactions.badge("", "RMA", ("#eeeeee", "#ffffff"))
        self.assertEqual(known.size, fallback.size)
        self.assertTrue(reactions.badge_runs("barcelona", "BAR", ("#aaaaaa", "#ffffff")))

    def test_pixel_ball_frames_and_paused_stability(self):
        frames = [reactions.soccer_sprite(i) for i in range(4)]
        self.assertEqual(len({len(f) for f in frames}), 1)
        self.assertNotEqual(frames[0], frames[1])
        reaction = plan({"format": "sports_highlights", "sport": "soccer"})
        self.assertEqual(
            reactions.decorations(reaction, 1, "PAUSED"),
            reactions.decorations(reaction, 2, "PAUSED"),
        )
        self.assertNotEqual(
            reactions.decorations(reaction, 1, "PLAYING"),
            reactions.decorations(reaction, 2, "PLAYING"),
        )
        ball = reactions.decorations(reaction, 1, "PLAYING")
        self.assertTrue(all(shape[0] == "rectangle" for shape in ball))
        self.assertGreater(min(shape[1][1] for shape in ball), 200)

    def test_native_sprites_avoid_crest_pixel_items(self):
        p = plan(
            {
                "format": "sports_highlights",
                "sport": "soccer",
                "participants": [
                    {"name": "Sunderland", "crest": "sunderland"},
                    {"name": "Leeds", "crest": "leeds_united"},
                ],
            }
        )
        full = reactions.decorations(p, 1, "PLAYING")
        native = reactions.decorations(p, 1, "PLAYING", native_sprites=True)
        self.assertGreater(len(full), 100)
        self.assertEqual(native, [])

    def test_shared_prop_art_covers_every_preset(self):
        from pi import prop_art

        for preset in PRESETS:
            sprite = prop_art.sprite(prop_art.key({"prop": preset["prop"]}))
            self.assertEqual(sprite.size, (32, 32))
            self.assertIsNotNone(sprite.getbbox())
            self.assertEqual(sprite.getchannel("A").getextrema()[0], 0)
            self.assertGreater(sprite.getchannel("A").getextrema()[1], 200)
        self.assertEqual(prop_art.position(1, "PAUSED"), prop_art.position(2, "PAUSED"))
        self.assertEqual(prop_art.key({"prop": "ball", "sport": "american_football"}), "football")

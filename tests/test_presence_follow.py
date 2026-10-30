import unittest
from okabebot.presence_follow import FollowGate


def state(place="pi", **kw):
    return {"surfaces": {"phase": "pi", "current_location": place}, "busy": False, **kw}


class FollowTests(unittest.TestCase):
    def test_near_wins_and_cooldown(self):
        g = FollowGate(["pi", "tv"])
        g.worn(True, 100)
        self.assertTrue(g.choose("pi", state("tv"), 100, near=True))
        self.assertFalse(g.choose("tv", state(), 110))
        self.assertFalse(g.choose("tv", state(), 150))
        g.worn(True, 230)
        self.assertTrue(g.choose("tv", state(), 230))

    def test_busy_playing_unknown_and_same_block(self):
        for s in (
            state(busy=True),
            state(media={"is_playing": True}),
            state(music={"is_playing": True}),
            state(focus={"active": True}),
            state("phone"),
            {"surfaces": {"phase": "departing", "current_location": "pi"}},
            state("tv"),
        ):
            g = FollowGate(["pi", "tv"])
            g.worn(True, 100)
            self.assertFalse(g.choose("tv", s, 100))
        self.assertFalse(FollowGate(["pi", "tv"]).choose("other", state(), 100))

    def test_unworn_or_stale_blocks(self):
        g = FollowGate(["pi", "tv"])
        self.assertFalse(g.choose("tv", state(), 100))
        g.worn(True, 100)
        self.assertFalse(g.choose("tv", state(), 221))
        g.worn(False, 222)
        self.assertFalse(g.choose("tv", state(), 223))

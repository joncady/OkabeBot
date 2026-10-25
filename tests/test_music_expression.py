import unittest
from okabebot.music_expression import MusicExpression


class ExpressionTests(unittest.TestCase):
    def test_stable_levels_and_reset(self):
        for level, label in [(0, "calm"), (0.35, "lively"), (0.9, "energetic")]:
            model = MusicExpression()
            for _ in range(150):
                result = model.update(level, True)
            self.assertEqual(result["characteristic"], label)
            self.assertEqual(model.update(0, False)["characteristic"], "unknown")

    def test_single_peak_does_not_claim_energetic_music(self):
        model = MusicExpression()
        for _ in range(50):
            model.update(0, True)
        self.assertEqual(model.update(1, True)["characteristic"], "calm")

import unittest

from okabebot.amadeus_evaluation import daily_review, helpfulness


class EvaluationTests(unittest.TestCase):
    def test_transparent_dimensions_and_bounds(self):
        self.assertEqual(
            helpfulness(dict(timing=2, relevance=2, grounding=2, actionability=1, respect=2)), 9
        )
        for value in (True, -1, 3, float("nan")):
            with self.assertRaises(ValueError):
                helpfulness(
                    dict(timing=value, relevance=2, grounding=2, actionability=2, respect=2)
                )

    def test_silent_days_cannot_be_omitted_or_duplicated(self):
        row = dict(date="2030-01-01", overall_helpfulness=4, reason="Missed a useful opening")
        with self.assertRaises(ValueError):
            daily_review([row], ["2030-01-01", "2030-01-02"])
        with self.assertRaises(ValueError):
            daily_review([row, row], ["2030-01-01"])
        self.assertEqual(daily_review([row], ["2030-01-01"])["mean_helpfulness"], 4)

    def test_nan_and_unexplained_scores_rejected(self):
        for score, reason in ((float("nan"), "Invalid"), (8, "")):
            with self.assertRaises(ValueError):
                daily_review(
                    [dict(date="2030-01-01", overall_helpfulness=score, reason=reason)],
                    ["2030-01-01"],
                )

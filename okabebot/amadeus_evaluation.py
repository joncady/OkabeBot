"""Anchored, explicit reviewer scores; never infer satisfaction from silence."""

DIMENSIONS = ("timing", "relevance", "grounding", "actionability", "respect")


def helpfulness(components):
    """Five 0–2 judgments produce a transparent 0–10 proposal score."""
    if not isinstance(components, dict) or set(components) != set(DIMENSIONS):
        raise ValueError("Score all five helpfulness dimensions")
    if any(type(v) is not int or not 0 <= v <= 2 for v in components.values()):
        raise ValueError("Each dimension must be an integer from zero to two")
    return sum(components.values())


def daily_review(reviews, expected_days):
    """Include silent days and missed opportunities; do not cherry-pick delivered cards."""
    if not isinstance(reviews, list) or not reviews:
        raise ValueError("Provide explicit day reviews")
    days = [r.get("date") for r in reviews]
    if len(set(days)) != len(days) or set(days) != set(expected_days):
        raise ValueError("Review every expected day exactly once, including silent days")
    for row in reviews:
        value = row.get("overall_helpfulness")
        if type(value) not in (int, float) or not 0 <= value <= 10:
            raise ValueError("Daily helpfulness must be between zero and ten")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError("Explain benefit, friction and missed opportunities")
    return {
        "days": len(reviews),
        "mean_helpfulness": sum(r["overall_helpfulness"] for r in reviews) / len(reviews),
        "minimum_helpfulness": min(r["overall_helpfulness"] for r in reviews),
        "rating_source": "explicit_reviewer",
    }

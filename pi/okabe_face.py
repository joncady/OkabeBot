"""Compatibility facade; Okabe owns its implementation in characters/okabe."""

try:
    from okabebot.characters import get
except ImportError:
    from characters import get


def shapes(**state):
    return get("okabe").shapes(**state)

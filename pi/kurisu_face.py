"""Compatibility facade; Kurisu owns its implementation in characters/kurisu."""

try:
    from okabebot.characters import get
except ImportError:
    from characters import get


def shapes(**state):
    return get("kurisu").shapes(**state)

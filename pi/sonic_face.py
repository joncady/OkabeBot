"""Compatibility facade; Sonic owns its implementation in characters/sonic."""

try:
    from okabebot.characters import get
except ImportError:
    from characters import get


def shapes(**state):
    return get("sonic").shapes(**state)

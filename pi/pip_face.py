"""Compatibility character renderer; implementations live in character directories."""

try:
    from okabebot.characters import get, registry as registry
except ImportError:
    from characters import get, registry as registry
EMOTIONS = ("neutral", "happy", "curious", "concerned", "excited")
ACTIVITIES = ("idle", "listening", "thinking", "speaking")


def pip_shapes(**state):
    return get("pip").shapes(**state)


def shapes(style="okabe", **state):
    return get(style).shapes(**state)


def render(style="okabe", **state):
    return get(style).render(**state)

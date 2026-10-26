"""Intent-level scene API shared by UI, notifications and MCP callers."""

from .hardware import rpc as _rpc
from .profiles import current_character


def set_activity(activity="idle", emotion="neutral", intensity=None):
    profile = current_character()
    return rpc(
        {
            "op": "character",
            "activity": activity,
            "emotion": emotion,
            "intensity": profile["intensity"] if intensity is None else intensity,
            "style": profile["style"],
            "palette": profile["palette"],
        }
    )


def present(notification, duration=12):
    return rpc({"op": "notification", "notification": notification, "duration_seconds": duration})


def dismiss():
    return rpc({"op": "notification", "notification": None})


def rpc(data):
    result = _rpc(data)
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result


def set_deploying(active):
    return rpc({"op": "deployments", "active": bool(active)})


def set_music(music):
    return rpc({"op": "music", "music": music})

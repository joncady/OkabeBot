"""Intent-level scene API shared by UI, notifications and MCP callers."""

from .hardware import rpc as _rpc
from .profiles import current_character
from .config import state_dir
import json
import tempfile
import time


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
    if data.get("op") == "character":
        from .scene_sets import environment
        from .surface_registry import Registry
        from .locations import for_adapter

        registry = Registry()
        if registry.scene_world_enabled():
            selected = environment(
                for_adapter("pi"), data.get("style", current_character()["style"])
            )
            data = dict(data, environment=selected["set"] or "unassigned")
    result = _rpc(data)
    if result.get("error"):
        raise RuntimeError(result["error"])
    if data.get("op") == "character":
        # Failure to persist a visual projection must never turn an already
        # executed physical action into an apparent failure/retry.
        try:
            folder = state_dir()
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as f:
                json.dump(dict(data, updated_at=time.time()), f)
                from pathlib import Path

                path = Path(f.name)
            path.replace(folder / "character-live.json")
        except OSError:
            pass
    return result


def live():
    try:
        return json.loads((state_dir() / "character-live.json").read_text())
    except (OSError, ValueError):
        return {}


def set_deploying(active):
    return rpc({"op": "deployments", "active": bool(active)})


def set_music(music):
    return rpc({"op": "music", "music": music})


def wave(*, allow_during_media=False):
    """A bounded silent visual greeting; never presses the physical SwitchBot."""
    return rpc({"op": "gesture", "gesture": "wave", "allow_during_media": allow_during_media})

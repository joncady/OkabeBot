"""Built-in characters and a persistent selection shared by controller and MCP."""

import json
from .prompts import prompt
import tempfile
from pathlib import Path
from .config import get_config, state_dir

PROFILES = {
    "sonic": {
        "name": "Sonic",
        "style": "sonic",
        "default_voice": "warm",
        "welcome_persona": prompt("sonic-welcome-persona"),
        "persona": prompt("sonic-persona"),
    },
    "okabe": {
        "name": "Okabe",
        "style": "okabe",
        "default_voice": "calm",
        "welcome_persona": prompt("okabe-welcome-persona"),
        "persona": prompt("okabe-persona"),
    },
    "kurisu": {
        "name": "Kurisu",
        "style": "kurisu",
        "default_voice": "warm",
        "welcome_persona": prompt("kurisu-welcome-persona"),
        "persona": prompt("kurisu-persona"),
    },
    "pip": {
        "name": "Pip",
        "style": "pip",
        "default_voice": "warm",
        "welcome_persona": prompt("pip-welcome-persona"),
        "persona": prompt("pip-persona"),
    },
}


def selection():
    try:
        value = json.loads((state_dir() / "profile.json").read_text())["profile"]
        return value if isinstance(value, str) and value in PROFILES else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def personality():
    from .presence_control import read

    value = read(state_dir() / "personality.json", {})
    if not isinstance(value, dict):
        value = {}
    tone = value.get("tone", "subtle")
    return {
        "tone": tone if tone in ("plain", "subtle", "playful") else "subtle",
        "natural_tool_replies": value.get("natural_tool_replies", True) is True,
    }


def set_personality(data):
    if not isinstance(data, dict) or not data or set(data) - {"tone", "natural_tool_replies"}:
        raise ValueError("Choose supported conversation settings")
    if "tone" in data and data["tone"] not in ("plain", "subtle", "playful"):
        raise ValueError("Choose plain, subtle or playful")
    if "natural_tool_replies" in data and type(data["natural_tool_replies"]) is not bool:
        raise ValueError("Choose natural tool replies on or off")
    from .presence_control import write

    write(state_dir() / "personality.json", {**personality(), **data})
    return personality()


def current_character():
    result = dict(get_config()["character"])
    chosen = selection()
    if chosen:
        result.update(PROFILES[chosen])
    tone = personality()["tone"]
    guard = "Facts and usefulness come first. Never invent household events, sensor readings, device conditions or actions for character flavor. Do not use fictional lore as an answer about the real world. "
    if tone == "playful":
        result["persona"] = (
            guard + result["persona"] + " Humor is optional; no forced catchphrases."
        )
    else:
        flavors = {
            "okabe": "Warm with very occasional dry wit.",
            "kurisu": "Thoughtful, direct and gently warm.",
            "pip": "Friendly, curious and simple.",
            "sonic": "Relaxed, friendly and concise.",
        }
        result["persona"] = (
            guard
            + "You are "
            + result["name"]
            + ". Use natural everyday language. "
            + (
                flavors.get(result["style"], "Be warm and direct.")
                if tone == "subtle"
                else "No roleplay, jokes or character theatrics."
            )
            + " Answer directly; do not add lab, experiment, world-line or anomaly references unless the user asks about them."
        )
        result["welcome_persona"] = result["persona"]
    return result


def select_profile(name):
    if not isinstance(name, str) or (name not in PROFILES and name != "configured"):
        raise ValueError("Choose configured, okabe, kurisu, pip, or sonic")
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as f:
        json.dump({"profile": name}, f)
        tmp = Path(f.name)
    tmp.replace(folder / "profile.json")
    return current_character()

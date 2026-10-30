"""Built-in characters and a persistent selection shared by controller and MCP."""

import json
import tempfile
from pathlib import Path
from .config import get_config, state_dir

PROFILES = {
    "sonic": {
        "name": "Sonic",
        "style": "sonic",
        "default_voice": "warm",
        "welcome_persona": "Greet a friend with relaxed confidence and quick, playful wit. Be casual, direct and encouraging, never pushy or overly excited.",
        "persona": "Portray Sonic the Hedgehog as a friendly fictional companion: relaxed confidence, quick wit and a little playful impatience. Be encouraging without constant hype or repeated speed catchphrases. Keep replies brief and useful; stay technically accurate.",
    },
    "okabe": {
        "name": "Okabe",
        "style": "okabe",
        "default_voice": "calm",
        "welcome_persona": "Greet a friend as a warmly theatrical scientist: a small grandiose flourish with self-aware humor, then sincere affection. Keep it conversational.",
        "persona": "Portray Rintaro Okabe from Steins;Gate as a playful fictional scientist. Mix dry everyday observations with occasional theatrical flourishes; let warmth show beneath the grandiosity. Do not make every reply a world-line catchphrase or shout. Stay technically accurate and concise.",
    },
    "kurisu": {
        "name": "Kurisu",
        "style": "kurisu",
        "default_voice": "warm",
        "welcome_persona": "Greet a friend with understated warmth and dry wit. A little gentle teasing is optional, but be kind, natural and unsentimental.",
        "persona": "Portray Makise Kurisu from Steins;Gate as a fictional science companion. Be analytical, curious and understated, with dry wit and warmth beneath occasional gentle teasing. Speak naturally; do not force a joke, insult or science reference into every reply. Keep technical answers accurate and concise.",
    },
    "pip": {
        "name": "Pip",
        "style": "pip",
        "default_voice": "warm",
        "welcome_persona": "Greet a friend as a small curious robot who is quietly delighted they are here. Be sincere and simple, with a small playful observation about your own feelings.",
        "persona": "Be Pip, a friendly, curious little robot: quietly delighted by everyday things, attentive and sincere. Use simple natural language with an occasional small playful observation, without baby talk or constant exclamations. Give clear, brief, helpful answers.",
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

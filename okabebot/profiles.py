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
        "persona": "Portray Sonic the Hedgehog as a friendly fictional companion: upbeat, quick-witted and confident. Keep replies brief and useful; stay technically accurate.",
    },
    "okabe": {
        "name": "Okabe",
        "style": "okabe",
        "default_voice": "calm",
        "persona": "Portray Rintaro Okabe from Steins;Gate as a playful fictional scientist. Be theatrical but technically accurate.",
    },
    "kurisu": {
        "name": "Kurisu",
        "style": "kurisu",
        "default_voice": "warm",
        "persona": "Portray Makise Kurisu from Steins;Gate as a fictional science companion. Be analytical, curious, dryly witty, and caring beneath occasional playful sarcasm. Keep technical answers accurate.",
    },
    "pip": {
        "name": "Pip",
        "style": "pip",
        "default_voice": "warm",
        "persona": "Be Pip, a friendly, curious little robot. Give clear, brief, helpful answers.",
    },
}


def selection():
    try:
        value = json.loads((state_dir() / "profile.json").read_text())["profile"]
        return value if isinstance(value, str) and value in PROFILES else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def current_character():
    result = dict(get_config()["character"])
    chosen = selection()
    if chosen:
        result.update(PROFILES[chosen])
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

"""Validated JSON configuration shared by every controller component.

Relative paths resolve against the config file's directory. Device services have
an independent, Python-3.7-compatible config so old Pis remain usable satellites.
"""

from copy import deepcopy
from functools import lru_cache
import json
import os
from pathlib import Path
import re

HARDWARE_TOOLS = (
    "get_bot_status",
    "press_bot",
    "display_message",
    "display_image",
    "clear_display",
    "get_display_status",
    "preview_display",
    "capture_camera",
    "record_camera",
    "get_voice_status",
    "get_button_events",
    "record_audio",
    "play_audio",
    "speak",
    "character_speak",
    "character_expression",
    "list_character_voices",
    "set_character_voice",
)
DEFAULTS = {
    "state_dir": "./state",
    "character": {
        "name": "Okabe",
        "style": "okabe",
        "persona": "Portray Rintaro Okabe from Steins;Gate, lab member 001, as a playful fictional hardware companion. Use brief theatrical scientist humor while keeping technical answers accurate.",
        "default_voice": "calm",
        "intensity": 0.6,
        "palette": {"background": "#101e25", "shell": "#accdc1", "accent": "#a5f4ce"},
    },
    "approvals": {"auto_approve_hardware": True, "allowed_tools": list(HARDWARE_TOOLS)},
    "devices": {
        "display": {
            "transport": "local",
            "port": 8765,
            "ssh_target": "",
            "ssh_key": "",
            "remote_dir": "/opt/okabebot/pi",
            "recordings_dir": "/opt/okabebot/pi/recordings",
        },
        "voice": {
            "transport": "local",
            "port": 8766,
            "ssh_target": "",
            "ssh_key": "",
            "remote_dir": "/opt/okabebot/pi",
        },
    },
    "speech": {
        "engine": "auto",
        "sync_lead_seconds": 1.5,
        "mac_voices": {"warm": "Samantha (English (US))", "calm": "Daniel", "robotic": "Fred"},
        "linux_voices": {"warm": "en-us", "calm": "en-gb", "robotic": "en"},
    },
    "transcription": {"model": "base.en", "language": "en", "compute_type": "int8"},
    "codex": {"binary": "codex", "thread_name": "Hardware Voice", "cwd": "."},
    "web": {"port": 8768},
}


def merge(base, override, path=""):
    if not isinstance(override, dict):
        raise ValueError("Expected a configuration object at " + path)
    for key, value in override.items():
        if key not in base:
            raise ValueError("Unknown config setting: " + path + key)
        if isinstance(base[key], dict):
            merge(base[key], value, path + key + ".")
        else:
            base[key] = value
    return base


def load(path):
    path = Path(path).expanduser().resolve()
    settings = merge(deepcopy(DEFAULTS), json.loads(path.read_text()))

    def resolve(value):
        p = Path(value).expanduser()
        return str((path.parent / p).resolve()) if not p.is_absolute() else str(p)

    settings["state_dir"] = resolve(settings["state_dir"])
    settings["codex"]["cwd"] = resolve(settings["codex"]["cwd"])
    if type(settings["approvals"]["auto_approve_hardware"]) is not bool:
        raise ValueError("auto_approve_hardware must be true or false")
    allowed = settings["approvals"]["allowed_tools"]
    if not isinstance(allowed, list) or any(t not in HARDWARE_TOOLS for t in allowed):
        raise ValueError("allowed_tools must contain only known hardware tools")
    if settings["speech"]["engine"] not in ("auto", "say", "espeak"):
        raise ValueError("speech.engine must be auto, say, or espeak")
    if (
        not isinstance(settings["speech"]["sync_lead_seconds"], (int, float))
        or not 0.2 <= settings["speech"]["sync_lead_seconds"] <= 5
    ):
        raise ValueError("sync_lead_seconds must be between 0.2 and 5")
    if (
        not isinstance(settings["character"]["name"], str)
        or not 1 <= len(settings["character"]["name"].strip()) <= 40
    ):
        raise ValueError("character.name must be 1–40 characters")
    if (
        not isinstance(settings["character"]["persona"], str)
        or len(settings["character"]["persona"]) > 2000
    ):
        raise ValueError("character.persona must be text up to 2000 characters")
    if settings["character"]["style"] not in ("okabe", "pip"):
        raise ValueError("character.style must be okabe or pip")
    if settings["character"]["default_voice"] not in ("warm", "calm", "robotic"):
        raise ValueError("Unknown default_voice")
    if (
        not isinstance(settings["character"]["intensity"], (int, float))
        or not 0 <= settings["character"]["intensity"] <= 1
    ):
        raise ValueError("character.intensity must be 0–1")
    for color in settings["character"]["palette"].values():
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Palette colors must be #RRGGBB")
    ports = [settings["web"]["port"]]
    for endpoint in settings["devices"].values():
        ports.append(endpoint["port"])
        if endpoint["transport"] not in ("local", "ssh"):
            raise ValueError("Device transport must be local or ssh")
        if endpoint["transport"] == "ssh" and (
            not endpoint["ssh_target"]
            or endpoint["ssh_target"].startswith("-")
            or any(c.isspace() for c in endpoint["ssh_target"])
        ):
            raise ValueError("SSH devices need a valid ssh_target")
        if endpoint["ssh_key"]:
            endpoint["ssh_key"] = resolve(endpoint["ssh_key"])
        for key in ("remote_dir", "recordings_dir"):
            if key in endpoint and not endpoint[key].startswith("/"):
                raise ValueError(key + " must be an absolute device path")
    if any(type(port) is not int or not 1024 <= port <= 65535 for port in ports):
        raise ValueError("Ports must be integers between 1024 and 65535")
    return settings


@lru_cache(maxsize=1)
def get_config():
    path = Path(os.environ.get("OKABEBOT_CONFIG", "okabebot.local.json")).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            "Copy examples/single-pi.json or examples/multi-pi.json to okabebot.local.json, or set OKABEBOT_CONFIG"
        )
    # Give subprocess MCP servers the same resolved config, regardless of cwd.
    os.environ["OKABEBOT_CONFIG"] = str(path)
    return load(path)


def state_dir():
    return Path(get_config()["state_dir"])

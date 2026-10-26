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
    "set_speaker_volume",
    "snooze_notifications",
    "dismiss_notification",
    "set_notification_source",
    "list_spotify_devices",
    "create_reminder",
    "list_reminders",
    "cancel_reminder",
    "show_calendar_agenda",
    "list_echo_speakers",
    "speak_on_echo",
    "get_current_media",
    "get_device_health",
    "get_focus_session",
    "control_focus_session",
    "get_recent_notifications",
    "get_calendar_agenda",
    "get_content_reaction_presets",
    "set_content_context",
    "publish_notification",
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
APPROVABLE_TOOLS = HARDWARE_TOOLS + ("control_spotify",)
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
        "cloud_model": "gpt-4o-mini-tts",
        "cloud_voices": {"warm": "coral", "calm": "onyx", "robotic": "alloy"},
        "engine": "auto",
        "local_socket": "/tmp/okabebot-tts.sock",
        "worker_command": [],
        "worker_ready_timeout_seconds": 120,
        "sync_lead_seconds": 0.5,
        "mac_voices": {"warm": "Samantha (English (US))", "calm": "Daniel", "robotic": "Fred"},
        "linux_voices": {"warm": "en-us+f3", "calm": "en-gb", "robotic": "en"},
    },
    "transcription": {"model": "base.en", "language": "en", "compute_type": "int8", "beam_size": 5},
    "codex": {"binary": "codex", "thread_name": "Hardware Voice", "cwd": ".", "effort": "low"},
    "spotify": {
        "source": "api",
        "playback_control": False,
        "cast_host": "",
        "callback_port": 8769,
        "poll_seconds": 15,
        "device_name": "",
        "listen_along": True,
    },
    "notifications": {
        "github": "",
        "workflow_lookback_days": 30,
        "github_webhook_repositories": [],
        "github_queue_url": "",
        "github_queue_region": "us-west-2",
        "github_queue_profile": "",
        "github_polling": True,
        "calendar": "",
        "calendar_lead_minutes": 10,
        "agenda_time": "",
        "agenda_timezone": "local",
        "speak_important": True,
        "group_window_seconds": 3,
        "chime_gain": 0.25,
    },
    "web": {"port": 8768, "host": "127.0.0.1"},
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
    if not isinstance(allowed, list) or any(t not in APPROVABLE_TOOLS for t in allowed):
        raise ValueError("allowed_tools must contain only known hardware tools")
    if settings["speech"]["engine"] not in ("auto", "say", "espeak", "openai", "local"):
        raise ValueError("speech.engine must be auto, say, espeak, openai, or local")
    if not isinstance(settings["speech"]["local_socket"], str):
        raise ValueError("speech.local_socket must be a path")
    settings["speech"]["local_socket"] = resolve(settings["speech"]["local_socket"])
    command = settings["speech"]["worker_command"]
    if not isinstance(command, list) or any(
        not isinstance(a, str) or not a or "\0" in a for a in command
    ):
        raise ValueError("speech.worker_command must be an argv list")
    if (
        type(settings["speech"]["worker_ready_timeout_seconds"]) is not int
        or not 5 <= settings["speech"]["worker_ready_timeout_seconds"] <= 600
    ):
        raise ValueError("worker_ready_timeout_seconds must be 5–600")
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
    if settings["character"]["style"] not in ("okabe", "kurisu", "pip", "sonic"):
        raise ValueError("character.style must be okabe, kurisu, pip, or sonic")
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
    if (
        type(settings["transcription"]["beam_size"]) is not int
        or not 1 <= settings["transcription"]["beam_size"] <= 5
    ):
        raise ValueError("transcription.beam_size must be 1–5")
    if settings["codex"]["effort"] not in ("low", "medium", "high"):
        raise ValueError("codex.effort must be low, medium, or high")
    import ipaddress

    ipaddress.ip_address(settings["web"]["host"])
    if settings["web"]["host"] == "0.0.0.0":
        raise ValueError("Use a specific LAN address or 127.0.0.1 for web.host")
    notifications = settings["notifications"]
    if not isinstance(notifications["github_polling"], bool):
        raise ValueError("github_polling must be boolean")
    if not isinstance(notifications["agenda_time"], str) or (
        notifications["agenda_time"]
        and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", notifications["agenda_time"])
    ):
        raise ValueError("agenda_time must be empty or HH:MM")
    from zoneinfo import ZoneInfo

    if notifications["agenda_timezone"] != "local":
        try:
            ZoneInfo(notifications["agenda_timezone"])
        except (KeyError, ValueError, TypeError):
            raise ValueError("agenda_timezone must be local or an IANA timezone") from None
    for field in ("github_queue_url", "github_queue_region", "github_queue_profile"):
        if not isinstance(notifications[field], str):
            raise ValueError(field + " must be text")
    if notifications["github_queue_url"] and not re.fullmatch(
        r"https://sqs\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?/\d{12}/[A-Za-z0-9_-]+",
        notifications["github_queue_url"],
    ):
        raise ValueError("github_queue_url must be a regional AWS SQS standard queue URL")
    if not re.fullmatch(r"[a-z0-9-]+", notifications["github_queue_region"]):
        raise ValueError("Invalid AWS queue region")
    if notifications["github_queue_profile"].startswith("-") or any(
        c.isspace() for c in notifications["github_queue_profile"]
    ):
        raise ValueError("Invalid AWS queue profile")
    repositories = notifications["github_webhook_repositories"]
    if (
        not isinstance(repositories, list)
        or len(repositories) > 100
        or any(
            not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
            for repo in repositories
        )
    ):
        raise ValueError("github_webhook_repositories must be explicit owner/repository names")
    if (
        type(notifications["workflow_lookback_days"]) is not int
        or not 1 <= notifications["workflow_lookback_days"] <= 90
    ):
        raise ValueError("workflow_lookback_days must be 1–90")
    if (
        type(notifications["calendar_lead_minutes"]) is not int
        or not 1 <= notifications["calendar_lead_minutes"] <= 120
    ):
        raise ValueError("Calendar lead must be 1–120 minutes")
    if (
        type(notifications["group_window_seconds"]) not in (int, float)
        or not 0 <= notifications["group_window_seconds"] <= 10
    ):
        raise ValueError("group_window_seconds must be 0..10")
    if (
        type(notifications["chime_gain"]) not in (int, float)
        or not 0 <= notifications["chime_gain"] <= 1
    ):
        raise ValueError("chime_gain must be 0..1")
    if type(notifications["speak_important"]) is not bool:
        raise ValueError("speak_important must be boolean")
    if any(not isinstance(notifications[k], str) for k in ("github", "calendar")):
        raise ValueError("Notification sources must be strings")
    if (
        type(settings["spotify"]["poll_seconds"]) is not int
        or not 10 <= settings["spotify"]["poll_seconds"] <= 300
    ):
        raise ValueError("Spotify polling must be 10–300 seconds")
    if type(settings["spotify"]["playback_control"]) is not bool:
        raise ValueError("spotify.playback_control must be boolean")
    if type(settings["spotify"]["listen_along"]) is not bool:
        raise ValueError("spotify.listen_along must be boolean")
    if not isinstance(settings["spotify"]["device_name"], str):
        raise ValueError("Spotify device_name must be text")
    from .adapters.media import MEDIA_FACTORIES

    if settings["spotify"]["source"] not in MEDIA_FACTORIES:
        raise ValueError("Media source must match a registered adapter")
    if settings["spotify"]["source"] == "cast":
        ipaddress.ip_address(settings["spotify"]["cast_host"])
        if not settings["spotify"]["device_name"]:
            raise ValueError("Cast requires device_name")
    ports = [settings["web"]["port"], settings["spotify"]["callback_port"]]
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

"""Small dependency-free device configuration, compatible with Python 3.7."""

import json
import os
from pathlib import Path

DEFAULTS = {
    "display_port": 8765,
    "display_keep_awake": True,
    "voice_port": 8766,
    "switchbot_address": "",
    "audio_device": "default",
    "audio_mixer_control": "Master",
    "audio_mixer_card": "",
    "button_backend": "gpiozero",
    "button_pin": 23,
    "led_pin": 25,
    "camera_backend": "auto",
    "room_sensor_port": "",
}


def load():
    path = Path(
        os.environ.get("OKABEBOT_DEVICE_CONFIG", str(Path(__file__).parent / "device.local.json"))
    )
    result = dict(DEFAULTS)
    if path.exists():
        data = json.loads(path.read_text())
        unknown = set(data) - set(DEFAULTS)
        if unknown:
            raise ValueError("Unknown device settings: " + ", ".join(sorted(unknown)))
        result.update(data)
    return result

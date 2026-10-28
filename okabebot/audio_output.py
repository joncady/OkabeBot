"""Selectable audio sinks and short-lived, read-only Sonos clip capabilities."""

import asyncio
import ipaddress
import json
from pathlib import Path
import re
import secrets
import tempfile
import time
import wave

from .config import get_config, state_dir


def preferences(update=None):
    path = state_dir() / "audio-routing.json"
    settings = {"reply": "pi", "announcement": "pi", "beam_volume": 20}
    if path.exists():
        settings.update(json.loads(path.read_text()))
    if update is not None:
        if not isinstance(update, dict) or set(update) - set(settings):
            raise ValueError("Unknown audio preference")
        settings.update(update)
    if any(settings[k] not in ("pi", "beam") for k in ("reply", "announcement")):
        raise ValueError("Choose Pi or Beam")
    volume = settings["beam_volume"]
    if type(volume) is not int or not 0 <= volume <= 100:
        raise ValueError("Beam announcement volume must be 0–100")
    if "beam" in (settings["reply"], settings["announcement"]):
        if not get_config()["audio"]["sonos_host"]:
            raise ValueError("Configure a Sonos host before selecting Beam")
    if update is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
            json.dump(settings, f)
            tmp = Path(f.name)
        tmp.chmod(0o600)
        tmp.replace(path)
    return dict(settings, beam_configured=bool(get_config()["audio"]["sonos_host"]))


def target(purpose):
    if purpose not in ("reply", "announcement"):
        raise ValueError("Unknown audio purpose")
    return preferences()[purpose]


class Clips:
    TTL = 180

    def __init__(self, folder):
        self.folder = Path(folder) / "audio-clips"
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)

    def put(self, pcm):
        if not isinstance(pcm, bytes) or not 4800 <= len(pcm) <= 30 * 48000 or len(pcm) % 2:
            raise ValueError("Expected bounded mono 24 kHz PCM")
        for p in self.folder.glob("*.wav"):
            if (
                re.fullmatch(r"[a-f0-9]{48}\.wav", p.name)
                and time.time() - p.stat().st_mtime > self.TTL
            ):
                p.unlink(missing_ok=True)
        key = secrets.token_hex(24)
        path = self.folder / (key + ".wav")
        with wave.open(str(path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(24000)
            f.writeframes(pcm)
        path.chmod(0o600)
        return key

    def read(self, key):
        if not re.fullmatch(r"[a-f0-9]{48}", key):
            raise ValueError("Invalid clip capability")
        path = self.folder / (key + ".wav")
        if time.time() - path.stat().st_mtime > self.TTL:
            raise ValueError("Clip expired")
        return path.read_bytes()


async def _sonos_clip(host, url, volume):
    from aiohttp import WSMsgType
    from sonos_websocket import SonosWebsocket

    # The upstream convenience client retries commands. Override it so an
    # uncertain loadAudioClip acknowledgement can never double an announcement.
    class OneShot(SonosWebsocket):
        async def send_command(self, command, options=None):
            if not self.ws or self.ws.closed:
                await self.connect()
            await self.ws.send_json([command, options or {}])
            msg = await self.ws.receive(timeout=8)
            if msg.type != WSMsgType.TEXT:
                raise RuntimeError("Sonos outcome unknown; no retry")
            return msg.json()

    ip = ipaddress.ip_address(host)
    if not ip.is_private or ip.is_loopback or ip.is_multicast:
        raise ValueError("Sonos requires a private LAN address")
    client = OneShot(host)
    try:
        response, data = await client.play_clip(url, volume=volume)
        if not response.get("success"):
            raise RuntimeError("Sonos rejected audio overlay; current playback was not replaced")
        return {"accepted": True, "clip_id": data.get("id"), "playback_confirmed": False}
    finally:
        await client.close()


def play(pcm):
    settings = preferences()
    if settings["beam_volume"] == 0:
        return {"muted": True, "accepted": False, "playback_confirmed": False}
    cfg = get_config()
    host = cfg["audio"]["sonos_host"]
    key = Clips(state_dir()).put(pcm)
    base = cfg["audio"]["media_base_url"] or (
        "http://%s:%s" % (cfg["web"]["host"], cfg["web"]["port"])
    )
    url = base.rstrip("/") + "/audio/clips/" + key + ".wav"
    return asyncio.run(_sonos_clip(host, url, settings["beam_volume"]))


def resolve(purpose):
    from .controller_tools import request

    # A failed handoff must not become speech on an unrelated fallback speaker.
    return request("/audio/resolve", {"purpose": purpose}, timeout=12)


class BrowserStream:
    def __init__(self, device_id):
        self.device_id = device_id

    def __call__(self, command):
        from .controller_tools import request

        return request(
            "/audio/stream",
            {"device_id": self.device_id, "command": command},
            timeout=40 if command.get("op") == "stream_end" else 10,
        )

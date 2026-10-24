"""MCP audio tools for a local or SSH-connected voice service."""

import base64
from pathlib import Path
import tempfile
import uuid
import wave
from mcp.types import ToolAnnotations

from .config import state_dir
from .transport import device
from .speech import normalize, synthesize


def rpc(data):
    response = device("voice").rpc(data)
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response


def play(path):
    source = Path(path).expanduser().resolve(strict=True)
    if source.stat().st_size > 20_000_000:
        raise ValueError("Audio source must be under 20 MB")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "normalized.wav"
        normalize(source, target)
        with wave.open(str(target)) as w:
            duration = w.getnframes() / w.getframerate()
        if not 0 < duration <= 30:
            raise ValueError("Audio must be no longer than 30 seconds")
        return rpc({"op": "play", "wav_base64": base64.b64encode(target.read_bytes()).decode()})


def register(mcp):
    read = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    action = ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    )

    @mcp.tool(annotations=read)
    def get_voice_status() -> dict:
        """Read the AIY button state, session ID, recent events, and audio busy flag."""
        return rpc({"op": "status"})

    @mcp.tool(annotations=read)
    def get_button_events(after_id: int = 0) -> dict:
        """Read button press/release events after an ID without consuming them.
        At most 100 recent events are kept. IDs reset when session_id changes;
        then restart from after_id=0. When the push-to-talk bridge is running,
        holding this button records speech and release sends it to Hardware Voice.
        """
        if after_id < 0:
            raise ValueError("after_id must be nonnegative")
        return rpc({"op": "events", "after_id": after_id})

    @mcp.tool(annotations=action)
    def record_audio(duration_seconds: int = 5) -> dict:
        """Record the Voice-kit microphone for 1–20 seconds, save mono 16kHz WAV
        on the controller, and return its absolute path. No automatic transcription.
        """
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 20:
            raise ValueError("duration_seconds must be 1–20")
        data = rpc({"op": "record", "duration_seconds": duration_seconds})
        folder = state_dir() / "audio"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (uuid.uuid4().hex + ".wav")
        path.write_bytes(base64.b64decode(data["wav_base64"], validate=True))
        return {
            "local_path": str(path),
            "duration_seconds": data["duration_seconds"],
            "sample_rate": 16000,
            "channels": 1,
        }

    @mcp.tool(annotations=action)
    def play_audio(path: str) -> dict:
        """Play a local controller audio file on the AIY speaker (maximum 30 seconds).
        Uses afconvert on macOS or ffmpeg on Linux. No remote URLs are fetched.
        """
        return play(path)

    @mcp.tool(annotations=action)
    def speak(text: str) -> dict:
        """Speak up to 300 characters through the AIY speaker using the configured local speech backend. No cloud speech service required."""
        if not text.strip() or len(text) > 300:
            raise ValueError("Text must be 1–300 characters")
        with tempfile.TemporaryDirectory() as tmp:
            audiofile = Path(tmp) / "speech.wav"
            from .character import current_voice

            synthesize(text, "neutral", current_voice(), audiofile)
            return play(str(audiofile))

"""Character expression, local speech synthesis, and coordinated playback."""

from .profiles import current_character

import array
import base64
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import math
from pathlib import Path
import tempfile
import time
from typing import Literal
import wave

from .hardware import rpc as display_rpc
from .voice import rpc as voice_rpc
from .config import get_config, state_dir
from . import speech, timing

Emotion = Literal["neutral", "happy", "curious", "concerned", "excited"]
Voice = Literal["default", "pip", "warm", "calm", "robotic"]
VOICES = speech.PRESETS
EMOTIONS = ("neutral", "happy", "curious", "concerned", "excited")


def preference_path():
    return state_dir() / "character.json"


def current_voice():
    try:
        name = json.loads(preference_path().read_text())["voice"]
        return name if name in VOICES else current_character()["default_voice"]
    except (OSError, ValueError, KeyError):
        return current_character()["default_voice"]


def set_voice(voice):
    if voice not in VOICES:
        raise ValueError("Choose warm, calm, or robotic")
    CONFIG = preference_path()
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=CONFIG.parent, delete=False) as f:
        json.dump({"voice": voice}, f)
        tmp = Path(f.name)
    tmp.replace(CONFIG)
    return {"voice": voice, "system_voice": speech.voices()[voice]}


def synthesize(text, emotion, voice, target):
    if not text.strip() or len(text) > 600:
        raise ValueError("Speech must be 1–600 characters")
    if emotion not in EMOTIONS or voice not in ("default", "pip", *VOICES):
        raise ValueError("Unknown emotion or voice")
    selected = current_voice() if voice in ("default", "pip") else voice
    speech.synthesize(text, emotion, selected, target)
    return selected


def envelope(path):
    with wave.open(str(path)) as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
            raise ValueError("Expected mono 16kHz PCM")
        seconds = wav.getnframes() / 16000
        if not 0 < seconds <= 30:
            raise ValueError("Speech exceeds 30 seconds; use shorter sentences")
        values = array.array("h", wav.readframes(wav.getnframes()))
    import sys

    if sys.byteorder != "little":
        values.byteswap()
    rms = [
        math.sqrt(sum(x * x for x in values[i : i + 800]) / len(values[i : i + 800]))
        for i in range(0, len(values), 800)
    ]
    peak = max(rms, default=1)
    return [round(min(1, (v / max(peak, 1)) ** 0.65), 3) if v > 100 else 0 for v in rms], seconds


def speak(text, emotion="neutral", intensity=None, voice="default"):
    if intensity is None:
        intensity = current_character()["intensity"]
    if (
        not isinstance(intensity, (int, float))
        or not math.isfinite(intensity)
        or not 0 <= intensity <= 1
    ):
        raise ValueError("intensity must be 0–1")
    speech_started = time.time()
    metrics = {"started_at": speech_started, "backend": speech.engine()}
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "character-speech.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("The character is already speaking")
        if speech.engine() == "openai":
            return stream_speak(text, emotion, intensity, voice, metrics)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "speech.wav"
            selected = synthesize(text, emotion, voice, path)
            metrics["synthesis_s"] = round(time.time() - speech_started, 3)
            timing.write("speech", metrics)
            levels, seconds = envelope(path)
            start = time.time() + get_config()["speech"]["sync_lead_seconds"]
            with ThreadPoolExecutor(max_workers=2) as pool:
                face = pool.submit(
                    display_rpc,
                    {
                        "op": "character",
                        "emotion": emotion,
                        "intensity": intensity,
                        "palette": current_character()["palette"],
                        "style": current_character()["style"],
                        "activity": "speaking",
                        "envelope": levels,
                        "start_at": start,
                    },
                )
                audio = pool.submit(
                    voice_rpc,
                    {
                        "op": "play",
                        "start_at": start,
                        "wav_base64": base64.b64encode(path.read_bytes()).decode(),
                    },
                )
                try:
                    played = audio.result()
                except Exception:
                    display_rpc({"op": "character", "emotion": emotion, "activity": "idle"})
                    raise
                face_result = face.result()
            metrics["total_s"] = round(time.time() - speech_started, 3)
            metrics["audio_s"] = seconds
            metrics["playback_started_at"] = played.get("playback_started_at")
            timing.write("speech", metrics)
            return {
                "spoken": bool(played.get("played")),
                "emotion": emotion,
                "voice": selected,
                "duration_seconds": seconds,
                "animation": "error" not in face_result,
                "display_error": face_result.get("error"),
            }


def stream_speak(text, emotion, intensity, voice, metrics):
    if (
        not text.strip()
        or len(text) > 600
        or emotion not in EMOTIONS
        or voice not in ("default", "pip", *VOICES)
    ):
        raise ValueError("Invalid speech text, emotion, or voice")
    selected = current_voice() if voice in ("default", "pip") else voice
    stream_id = None
    total = 0
    levels = []
    face_pool = ThreadPoolExecutor(max_workers=1)
    face_future = None
    character = current_character()
    try:
        for sequence, chunk in enumerate(speech.pcm_chunks(text, emotion, selected)):
            if stream_id is None:
                metrics["first_chunk_s"] = round(time.time() - metrics["started_at"], 3)
                stream_id = voice_rpc({"op": "stream_start"})["stream_id"]
                character = current_character()
                display_rpc(
                    {
                        "op": "character",
                        "activity": "speaking",
                        "emotion": emotion,
                        "style": character["style"],
                        "palette": character["palette"],
                        "intensity": intensity,
                    }
                )
            result = voice_rpc(
                {
                    "op": "stream_chunk",
                    "stream_id": stream_id,
                    "sequence": sequence,
                    "pcm_base64": base64.b64encode(chunk).decode(),
                }
            )
            values = array.array("h", chunk)
            import sys

            if sys.byteorder == "big":
                values.byteswap()
            for offset in range(0, len(values), 1200):
                block = values[offset : offset + 1200]
                rms = math.sqrt(sum(x * x for x in block) / len(block))
                levels.append(round(min(1, rms / 5000), 3))
            total += len(chunk)
            if face_future is None or face_future.done():
                face_future = face_pool.submit(
                    display_rpc,
                    {
                        "op": "character",
                        "activity": "speaking",
                        "emotion": emotion,
                        "style": character["style"],
                        "palette": character["palette"],
                        "intensity": intensity,
                        "envelope": list(levels),
                        "start_at": result["playback_started_at"],
                    },
                )
            metrics["playback_started_at"] = result.get("playback_started_at")
            if sequence == 0:
                timing.write("speech", metrics)
        if stream_id is None:
            raise RuntimeError("Speech provider returned no audio")
        result = voice_rpc({"op": "stream_end", "stream_id": stream_id})
        metrics.update(total_s=round(time.time() - metrics["started_at"], 3), audio_s=total / 48000)
        timing.write("speech", metrics)
        return {
            "spoken": result.get("played", False),
            "voice": selected,
            "emotion": emotion,
            "duration_seconds": total / 48000,
        }
    except Exception:
        if stream_id:
            try:
                voice_rpc({"op": "stream_abort", "stream_id": stream_id})
            except Exception:
                pass
        raise
    finally:
        face_pool.shutdown(wait=True)
        display_rpc({"op": "character", "activity": "idle", "emotion": emotion})


def register(mcp):
    from mcp.types import ToolAnnotations

    action = ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    )

    @mcp.tool(annotations=action)
    def character_speak(
        text: str,
        emotion: Emotion = "neutral",
        intensity: float | None = None,
        voice: Voice = "default",
    ) -> dict:
        """Speak as the configured character on the AIY speaker with a matching face and animated mouth
        on the display Pi. Choose emotion to match the reply, not infer the user's
        feelings. Keep text under 600 characters / 30 seconds. voice=default uses the
        user's saved preference. Do not also call speak for the same reply.
        After success, put the spoken text in the final answer; the bridge skips
        duplicate playback. Do not automatically retry uncertain playback.
        """
        return speak(text, emotion, intensity, voice)

    @mcp.tool(annotations=action)
    def character_expression(
        emotion: Emotion = "neutral",
        intensity: float | None = None,
        activity: Literal["idle", "listening", "thinking"] = "idle",
    ) -> dict:
        """Show the configured character with an emotion and activity, without speaking. Replaces screen content."""
        if intensity is None:
            intensity = current_character()["intensity"]
        return display_rpc(
            {
                "op": "character",
                "emotion": emotion,
                "intensity": intensity,
                "palette": current_character()["palette"],
                "style": current_character()["style"],
                "activity": activity,
            }
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_character_voices() -> dict:
        """List the character's three locally installed voice presets and saved default."""
        return {"default": current_voice(), "voices": speech.voices()}

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
        )
    )
    def set_character_voice(voice: Literal["warm", "calm", "robotic"]) -> dict:
        """Save the character's default voice when the user chooses one. Does not play a sample."""
        return set_voice(voice)

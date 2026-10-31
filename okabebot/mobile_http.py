"""Android-only capabilities: no owner token, arbitrary moves or home controls."""

import base64
import io
import json
import tempfile
import wave
from pathlib import Path
from urllib.parse import urlsplit


class NoSpeech(ValueError):
    pass


def handle(handler, bridge, post=False):
    path = urlsplit(handler.path).path
    if not path.startswith("/mobile/"):
        return False
    voice_identity, stage = None, None
    streaming = False

    def failed(error):
        if voice_identity:
            bridge.mobile.trace(voice_identity, "failed:" + str(stage), error)

    try:
        if handler.headers.get("Host") not in bridge.allowed_hosts:
            raise PermissionError("Invalid host")
        origin = handler.headers.get("Origin")
        if origin and urlsplit(origin).netloc != handler.headers.get("Host"):
            raise PermissionError("Invalid origin")
        if path in ("/mobile/settings", "/mobile/test"):
            if not handler.authorized():
                raise PermissionError("Owner access required")
            data = None
            if post:
                size = int(handler.headers.get("Content-Length", 0))
                if not 0 < size <= 1024:
                    raise ValueError("Invalid request size")
                handler.connection.settimeout(5)
                data = json.loads(handler.rfile.read(size))
            if path == "/mobile/test":
                if not post or not isinstance(data, dict) or set(data) != {"id"}:
                    raise ValueError("Choose one test destination")
                handler.respond(200, bridge.mobile.test(data["id"]))
            else:
                handler.respond(200, bridge.mobile.settings(data))
            return True
        secret = handler.headers.get("X-Surface-Token", "")
        bridge.mobile.device(secret)
        if not post and path == "/mobile/status":
            handler.respond(200, bridge.mobile.voice_status(secret))
            return True
        if not post and path == "/mobile/inbox":
            handler.respond(200, bridge.mobile.inbox(secret))
            return True
        if not post and path == "/mobile/suggestion":
            result = bridge.proactive.explanation()
            bridge.mobile.device(secret)  # Revocation during the read withholds private context.
            handler.respond(200, result)
            return True
        if not post or path not in (
            "/mobile/push",
            "/mobile/chat",
            "/mobile/voice",
            "/mobile/feedback",
        ):
            handler.respond(404, {"error": "Unknown mobile operation"})
            return True
        if path == "/mobile/voice":
            bridge.mobile.voice_available(secret)
            voice_identity, stage = bridge.mobile.device(secret)["id"], "receiving"
            bridge.mobile.trace(voice_identity, stage)
        size = int(handler.headers.get("Content-Length", 0))
        if not 0 < size <= (950000 if path == "/mobile/voice" else 8192):
            raise ValueError("Invalid request size")
        handler.connection.settimeout(10)
        data = json.loads(handler.rfile.read(size))
        if path == "/mobile/push":
            result = bridge.mobile.configure(secret, data)
        elif path == "/mobile/feedback":
            if (
                not isinstance(data, dict)
                or set(data) != {"suggestion_id", "outcome"}
                or not isinstance(data["suggestion_id"], str)
                or len(data["suggestion_id"]) != 32
                or any(c not in "0123456789abcdef" for c in data["suggestion_id"])
                or data["outcome"] not in ("good_timing", "too_soon", "not_interested")
            ):
                raise ValueError("Choose feedback for one check-in")
            result = bridge.proactive.suggestion_feedback(data)
        else:
            generate = getattr(bridge.codex, "compose_preference", None)
            if path == "/mobile/voice":
                item = bridge.mobile.device(secret)
                if bridge.surfaces.phase != "tv" or bridge.surfaces.active_id != item["id"]:
                    raise PermissionError("Call the companion to this phone first")
                if (
                    not isinstance(data, dict)
                    or not {"clip_id", "wav_base64"} <= set(data)
                    or set(data) - {"clip_id", "wav_base64", "playback_mode"}
                    or data.get("playback_mode", "wav") not in ("wav", "stream")
                ):
                    raise ValueError("Provide a recorded clip")
                streaming = data.get("playback_mode") == "stream"
                raw = base64.b64decode(data["wav_base64"], validate=True)
                if len(raw) > 700000:
                    raise ValueError("Recording too large")
                with wave.open(io.BytesIO(raw)) as wav:
                    if (
                        wav.getparams()[:3] != (1, 2, 16000)
                        or not 0 < wav.getnframes() <= 320000
                        or len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2
                    ):
                        raise ValueError("Use bounded mono 16kHz PCM")
                with tempfile.TemporaryDirectory(prefix="amadeus-mobile-") as tmp:
                    clip = Path(tmp) / "input.wav"
                    clip.write_bytes(raw)
                    stage = "transcribing"
                    bridge.mobile.trace(voice_identity, stage)
                    text = bridge.transcribe(clip)
                if not text.strip():
                    stage = "transcribing"
                    raise NoSpeech("No clear speech")
                data = {"text": text, "request_id": data["clip_id"]}
                stage = "generating"
                bridge.mobile.trace(voice_identity, stage)
            from .local_conversation import READ_TOOLS

            turn = getattr(bridge.codex, "text_turn", None)
            specs = {k: v for k, v in getattr(bridge.codex, "specs", {}).items() if k in READ_TOOLS}
            result = bridge.mobile.chat(
                secret,
                data,
                generate,
                tool_turn=(lambda text, **kw: turn(text, read_only=True, **kw)) if turn else None,
                specs=specs,
            )
            if path == "/mobile/voice":
                stage = "synthesizing"
                bridge.mobile.trace(voice_identity, stage)
                # Private reply only, never the currently active home speaker.
                from .character import synthesize, envelope

                bridge.mobile.device(secret)
                if bridge.surfaces.phase != "tv" or bridge.surfaces.active_id != item["id"]:
                    raise PermissionError("The phone audio session ended before speech generation")
                if streaming:
                    result.update(
                        bridge.mobile.start_voice_stream(
                            secret, result["reply"], bridge.surface_audio, bridge.surfaces
                        )
                    )
                    result["timings"] = bridge.mobile.voice_status(secret)
                    try:
                        handler.respond(200, result)
                    except OSError:
                        bridge.mobile.cancel_voice_stream(voice_identity)
                        raise
                    return True
                from .speech import synthesis_session

                with (
                    synthesis_session(),
                    tempfile.TemporaryDirectory(prefix="amadeus-mobile-") as tmp,
                ):
                    audio = Path(tmp) / "reply.wav"
                    synthesize(result["reply"][:550], "neutral", "default", audio)
                    bridge.mobile.device(secret)
                    if bridge.surfaces.phase != "tv" or bridge.surfaces.active_id != item["id"]:
                        raise PermissionError(
                            "Companion has moved; audio is not replayed elsewhere"
                        )
                    levels, seconds = envelope(audio)
                    result.update(levels=levels, seconds=seconds)
                    result["wav_base64"] = base64.b64encode(audio.read_bytes()).decode()
                bridge.mobile.trace(voice_identity, "ready")
                result["timings"] = bridge.mobile.voice_status(secret)
        handler.respond(200, result)
    except PermissionError:
        failed("authorization_or_location")
        handler.respond(
            403,
            {
                "error": "Approve this Android screen and enable private Amadeus conversation consent."
                if path in ("/mobile/suggestion", "/mobile/feedback")
                else "Approve this Android screen and keep the companion here until the reply finishes"
            },
        )
    except NoSpeech:
        failed("no_clear_speech")
        handler.respond(
            422,
            {
                "error": "Recording had no clear speech. Tap once to start, speak while the mic is active, then tap again to send."
            },
        )
    except (ValueError, TypeError, KeyError, wave.Error) as exc:
        messages = {
            "Voice worker is busy; try a new recording after speech finishes": "Voice worker is busy. Wait for speech to finish before starting a new recording.",
            "Enable preference conversations in private Amadeus setup first": "Enable preference conversations in private Amadeus setup first.",
            "Already submitted; no automatic retry": "This recording was already submitted. Start a new recording; it was not sent twice.",
            "Local conversation worker unavailable": "The local conversation worker is unavailable. Please try a new recording later.",
        }
        message = messages.get(str(exc))
        failed(
            "conversation_consent"
            if str(exc).startswith("Enable preference conversations")
            else "invalid_request"
        )
        handler.respond(
            400,
            {
                "error": "Feedback was not confirmed. Refresh the check-in before sending again."
                if path == "/mobile/feedback"
                else "Private check-in details are unavailable. Check Amadeus conversation consent."
                if path == "/mobile/suggestion"
                else message
                or "This recording could not be processed. Start a new recording; no automatic retry."
            },
        )
    except Exception as exc:
        failed(type(exc).__name__)
        handler.respond(
            503,
            {
                "error": "Voice generation failed. No audio will be automatically retried."
                if stage == "synthesizing"
                else "Mobile service unavailable; no request is pending or automatically retried"
            },
        )
    return True

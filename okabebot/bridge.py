"""Local push-to-talk control page, Whisper transcription, and Codex bridge."""

from .profiles import current_character, select_profile, selection

from contextlib import ExitStack
import argparse
import base64
import collections
import hmac
import json
import os
from pathlib import Path
import signal
import sqlite3
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import timing, scene, agenda
from .notifications import Inbox
from .notification_policy import NotificationPolicy
from .github_webhook import GitHubWebhook
from .github_queue import GitHubQueue, AwsQueueClient
from .focus import FocusTimer
from .sources import Sources
from .adapters.media import MediaSnapshot, create_media_source, begin_auth
from .content import ContentContext, ContentPreview, PRESETS
from .team_resolver import TeamResolver
from .movie_metadata import MovieMetadata
from .music_expression import MusicExpression
from .integration_auth import notification_token, may_publish, persistent_token
from .codex import Codex
from . import character as character_tools
from concurrent.futures import ThreadPoolExecutor
from .config import get_config, state_dir
from .transport import device


def runtime_folder():
    return state_dir() / "ptt"


class Bridge:
    def __init__(self, port, transcribe_only=False):
        self.resources = ExitStack()
        try:
            self._initialize(port, transcribe_only)
        except BaseException:
            self.resources.close()
            raise

    def _initialize(self, port, transcribe_only):
        self.folder = runtime_folder()
        config = get_config()
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        try:
            self.enabled = json.loads((state_dir() / "button-settings.json").read_text())["enabled"]
            if type(self.enabled) is not bool:
                self.enabled = True
        except (OSError, ValueError, KeyError):
            self.enabled = True
        self.closing = threading.Event()
        self.messages = collections.deque(maxlen=100)
        self.status = "Starting"
        self.face_worker = ThreadPoolExecutor(max_workers=1)
        self.resources.callback(self.face_worker.shutdown, wait=False, cancel_futures=True)
        self.face_activity = None
        self.recording = False
        self.processing = False
        self.timings = {}
        self.music_mic = config["spotify"]["listen_along"]
        self.music_meter = {}
        self.media_source = create_media_source(
            config["spotify"]["source"], state_dir(), config["spotify"]
        )
        self.media_state = MediaSnapshot()
        self.resources.callback(self.media_source.close)
        self.content_context = ContentContext(state_dir())
        self.content_preview = ContentPreview()
        self.team_resolver = TeamResolver(state_dir(), upload=scene.rpc)
        self.resources.callback(self.team_resolver.close)
        self.movie_metadata = MovieMetadata(state_dir())
        self.resources.callback(self.movie_metadata.close)
        self.content_parse = {}
        self.inbox = Inbox(state_dir(), config["notifications"]["group_window_seconds"])
        self.inbox.recover()
        self.notification_policy = NotificationPolicy(
            state_dir(), config["notifications"]["speak_important"]
        )
        self.github_webhook = GitHubWebhook(
            self.inbox, config["notifications"]["github_webhook_repositories"]
        )
        self.github_queue = None
        if config["notifications"]["github_queue_url"]:
            self.github_queue = GitHubQueue(
                self.github_webhook,
                AwsQueueClient(config["notifications"]),
                on_event=lambda: self.face_worker.submit(
                    scene.set_deploying, bool(self.deployments())
                ),
            )
            self.resources.callback(self.github_queue.close)
        from .application import Application

        self.application = Application(self)
        self.focus = FocusTimer(self.inbox)
        self.sources = Sources(self.inbox, state_dir(), config["notifications"])
        self.active_notification = None
        self.notification_until = 0
        self.announcing = False
        self.codex = None
        self.token = persistent_token(state_dir(), "controller-token")
        self.notification_token = notification_token(state_dir())
        self.arrival_token = persistent_token(state_dir(), "arrival-token")
        from .alexa_voice import AlexaVoice

        self.alexa_voice = AlexaVoice(state_dir(), config["alexa_voice"], self)
        self.port = port
        host = config["web"]["host"]
        import socket

        self.allowed_hosts = {"127.0.0.1:%s" % port, "localhost:%s" % port, host + ":" + str(port)}
        hostname = socket.gethostname().split(".")[0]
        self.allowed_hosts.add(hostname + ".local:" + str(port))
        self.allowed_hosts.update(config["web"].get("allowed_hosts", []))
        self.allowed_hosts.update(value.lower() for value in list(self.allowed_hosts))
        from .surfaces import Surfaces

        self.surfaces = Surfaces(scene.rpc, lambda: getattr(self.media_source, "cast", None))
        self.resources.callback(self.surfaces.close)
        from .surface_audio import AudioHub

        self.surface_audio = AudioHub()
        self.voice_rpc = device("voice").rpc
        self.device_health = {
            name: {"available": False, "error": "Connecting"} for name in ("voice", "display")
        }
        self.speech_health = {"available": False, "error": "Checking voice backend"}
        self.speaker_volume = {"available": False, "percent": None}
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            config["transcription"]["model"],
            device="cpu",
            compute_type=config["transcription"]["compute_type"],
            download_root=str(state_dir() / "models"),
            local_files_only=True,
        )
        if not transcribe_only:
            if config["conversation"]["backend"] == "local":
                from .local_conversation import LocalConversation

                self.codex = LocalConversation(self.folder, self.notify, self.reply)
            else:
                self.codex = Codex(self.folder, self.notify, self.reply)
            self.resources.callback(self.codex.close)
        with sqlite3.connect(self.folder / "clips.sqlite3") as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS clips (id TEXT PRIMARY KEY, status TEXT, transcript TEXT)"
            )
        self.status = "Ready — hold the button to talk"
        self.show_activity("idle")
        (self.folder / "control.json").write_text(json.dumps({"url": self.url, "pid": os.getpid()}))
        os.chmod(self.folder / "control.json", 0o600)
        if self.github_queue:
            self.github_queue.start()
        threading.Thread(target=self.poll, daemon=True).start()
        threading.Thread(target=self.poll_sources, daemon=True).start()
        threading.Thread(target=self.poll_music, daemon=True).start()
        threading.Thread(target=self.poll_music_meter, daemon=True).start()
        threading.Thread(target=self.poll_health, daemon=True).start()

    @property
    def url(self):
        return "http://%s:%s/#%s" % (get_config()["web"]["host"], self.port, self.token)

    def pi(self, data):
        try:
            result = self.voice_rpc(data)
            if result.get("error") and "armed" not in result:
                raise RuntimeError(result["error"])
            self.device_health["voice"] = {"available": True, "error": None}
            return result
        except Exception:
            self.device_health["voice"] = {
                "available": False,
                "error": "Unavailable — reconnecting",
            }
            raise

    def poll_health(self):
        while not self.closing.is_set():
            busy = self.processing or self.announcing or (self.codex and self.codex.busy)
            if not busy:
                self.speech_health = character_tools.speech.health()
            for name in ("voice", "display"):
                try:
                    result = device(name).rpc({"op": "status"})
                    if result.get("error"):
                        raise RuntimeError("Device status unavailable")
                    self.device_health[name] = {"available": True, "error": None}
                    if name == "display" and result.get("kind") == "idle":
                        # A reboot clears the Pi canvas even when the desired activity is unchanged.
                        self.face_worker.submit(scene.set_activity, self.face_activity or "idle")
                    if name == "voice":
                        self.speaker_volume = result.get("volume", self.speaker_volume)
                except Exception:
                    self.device_health[name] = {
                        "available": False,
                        "error": "Unavailable — reconnecting",
                    }
            self.closing.wait(5)

    def notify(self, kind, data):
        if kind == "local_model":
            self.timings["local_generation_s"] = data["selection_s"]
        if kind == "local_execution":
            self.timings["local_tool_s"] = data["duration_s"]
        if (
            kind == "assistant"
            and "first_model_output_s" not in self.timings
            and self.timings.get("submitted_at")
        ):
            self.timings["first_model_output_s"] = round(
                time.time() - self.timings["submitted_at"], 3
            )
        if kind == "turn_completed":
            self.show_activity("idle")
        if kind == "turn_completed" and self.timings.get("submitted_at"):
            self.timings["codex_turn_s"] = round(time.time() - self.timings["submitted_at"], 3)
        if kind == "turn_completed" and getattr(self, "active_clip_id", None):
            values = dict(
                self.timings,
                backend=get_config()["conversation"]["backend"],
                status=data.get("status"),
            )
            spoken = timing.read("speech")
            if spoken.get("started_at", 0) >= values.get("clip_received_at", float("inf")):
                values["speech"] = spoken
            try:
                timing.append_turn(self.folder, self.active_clip_id, values)
            except Exception:
                pass  # Timing persistence must never retry or break an action.
        entry = {"kind": kind, "data": data, "time": time.time()}
        with self.lock:
            self.messages.append(entry)
            with (self.folder / "transcript.jsonl").open("a") as f:
                f.write(json.dumps(entry) + "\n")
            if kind == "approval":
                self.status = "Codex needs your input"
            if kind == "error":
                self.status = str(data.get("message", data))
        print(kind, json.dumps(data)[:500], flush=True)

    def show_activity(self, activity):
        if self.face_activity == activity:
            return
        self.face_activity = activity
        self.face_worker.submit(scene.set_activity, activity)

    def reply(self, text, status):
        if status != "completed":
            self.status = "Turn stopped — ready for your next message"
            return
        if not text.strip():
            self.status = "Ready — hold the button to talk"
            return
        self.status = "Speaking"
        try:
            spoken = text[:550]
            if len(text) > 550:
                spoken += ". The rest is on the control page."
            character_tools.speak(spoken)
            self.status = "Ready — hold the button to talk"
        except Exception as exc:
            self.notify("error", {"message": "Speaker: " + str(exc)})

    def submit_screen_clip(self, data):
        """Claim a bounded user-recorded WAV through the ordinary speech/tool path."""
        import re

        if set(data) != {"clip_id", "wav_base64"} or not re.fullmatch(
            r"screen-[A-Za-z0-9_-]{8,95}", data["clip_id"]
        ):
            raise ValueError("Invalid recording identity")
        raw = base64.b64decode(data["wav_base64"], validate=True)
        if len(raw) > 700000 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
            raise ValueError("Invalid recording")
        with self.lock:
            if (
                self.processing
                or self.recording
                or self.announcing
                or not self.codex
                or self.codex.busy
            ):
                raise ValueError("Wait until the current turn finishes")
            self.processing = True

        def submit():
            try:
                self.pi({"op": "ptt", "enabled": False})
                self.handle_clip(dict(data, released_at=time.time()))
            except Exception:
                self.notify("error", {"message": "Screen recording failed; no automatic replay"})
            finally:
                self.processing = False

        threading.Thread(target=submit, daemon=True).start()

    def transcribe(self, path):
        segments, _ = self.model.transcribe(
            str(path),
            language=get_config()["transcription"]["language"],
            beam_size=get_config()["transcription"]["beam_size"],
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(
            s.text.strip() for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1
        ).strip()

    def handle_clip(self, clip):
        handed_off = False
        try:
            handed_off = self._handle_clip(clip)
        finally:
            # Rejected/failed recordings never receive a turn_completed event.
            if not handed_off:
                self.show_activity("idle")

    def _handle_clip(self, clip):
        self.timings = {"clip_received_at": time.time()}
        if clip.get("released_at"):
            self.timings["release_to_clip_s"] = round(time.time() - clip["released_at"], 3)
        clip_id = clip["clip_id"]
        with sqlite3.connect(self.folder / "clips.sqlite3") as db:
            if db.execute("SELECT 1 FROM clips WHERE id=?", (clip_id,)).fetchone():
                return
            # Claim before transcription/submission: never replay a command after a crash.
            db.execute("INSERT INTO clips VALUES (?, ?, ?)", (clip_id, "claimed", ""))
        self.active_clip_id = clip_id
        self.status = "Transcribing"
        self.show_activity("thinking")
        raw = base64.b64decode(clip["wav_base64"], validate=True)
        if len(raw) > 700000:
            raise ValueError("Recording too large")
        with tempfile.TemporaryDirectory(prefix="hardware-ptt-") as tmp:
            path = Path(tmp) / "speech.wav"
            path.write_bytes(raw)
            started = time.monotonic()
            text = self.transcribe(path)
            self.timings["transcription_s"] = round(time.monotonic() - started, 3)
        if not text:
            self.notify("notice", {"text": "No clear speech detected. Please try again."})
            return
        self.notify("user", {"text": text, "clip_id": clip_id})
        with sqlite3.connect(self.folder / "clips.sqlite3") as db:
            db.execute(
                "UPDATE clips SET status=?, transcript=? WHERE id=?", ("transcribed", text, clip_id)
            )
        if self.codex:
            self.status = (
                "Local model" if get_config()["conversation"]["backend"] == "local" else "Codex"
            ) + " is working"
            self.timings["submitted_at"] = time.time()
            self.codex.submit(text)
            with sqlite3.connect(self.folder / "clips.sqlite3") as db:
                db.execute("UPDATE clips SET status=? WHERE id=?", ("submitted", clip_id))
            return True

    def poll_music(self):
        last = None
        refresh_at = 0
        display_session = None
        while not self.closing.is_set():
            try:
                snapshot = self.media_source.read()
                if not isinstance(snapshot, MediaSnapshot):
                    raise TypeError("Media adapter must return MediaSnapshot")
                self.media_state = snapshot
                self.sources.errors.pop("media_source", None)
            except Exception:
                self.sources.errors["media_source"] = "Media source unavailable; retrying"
                self.closing.wait(2)
                continue
            music = dict(self.media_state.music)
            tv = dict(self.media_state.video)
            self.content_parse = self.movie_metadata.get(tv, self.team_resolver.get(tv))
            if (
                tv.get("app") != "Spotify"
                and (tv.get("title") or tv.get("app"))
                and tv.get("state") in ("PLAYING", "PAUSED", "BUFFERING")
            ):
                if not tv.get("title"):
                    tv["title"] = "Title unavailable"
                    tv["position"] = None
                    tv["metadata_status"] = "title_unavailable"
                tv["reaction"] = self.content_context.get(
                    tv, fallback=self.content_parse.get("context", {})
                )
                music = dict(music, video=tv)
            music = self.content_preview.music() or music
            signature = json.dumps(
                {k: v for k, v in music.items() if k != "updated_at"}, sort_keys=True
            )
            if signature != last or time.monotonic() >= refresh_at:
                try:
                    if time.monotonic() >= refresh_at:
                        status = scene.rpc({"op": "status"})
                        session = status.get("session_id")
                        if session != display_session:
                            scene.set_activity()
                            scene.set_deploying(bool(self.deployments()))
                            with self.team_resolver.lock:
                                self.team_resolver.results.clear()
                            display_session = session
                    # Compensate delivery delay once, using the Mac clock. The Pi then
                    # advances from a local monotonic anchor without clock skew.
                    delivered = dict(music)
                    if music.get("video"):
                        v = dict(music["video"])
                        if v.get("state") == "PLAYING" and isinstance(
                            v.get("position"), (int, float)
                        ):
                            v["position"] += max(0, time.time() - v["updated_at"]) * v.get(
                                "playback_rate", 1
                            )
                        delivered["video"] = v
                    scene.set_music(delivered)
                    last = signature
                    refresh_at = time.monotonic() + 15
                    self.sources.errors.pop("media_display", None)
                except Exception:
                    self.sources.errors["media_display"] = "Media display unavailable; retrying"
            self.closing.wait(2)

    def poll_music_meter(self):
        expression = MusicExpression()
        last_sample = time.monotonic()
        # Dedicated persistent display connection avoids an SSH handshake per pulse.
        while not self.closing.is_set():
            try:
                with device("display").connect() as display:
                    while not self.closing.is_set():
                        enabled = bool(
                            self.music_mic
                            and self.media_state.music.get("is_playing")
                            and not self.recording
                            and not self.processing
                            and not self.announcing
                            and not (self.codex and self.codex.busy)
                        )
                        self.music_meter = self.pi({"op": "music_meter", "enabled": enabled})
                        now = time.monotonic()
                        mood = expression.update(
                            self.music_meter.get("level", 0),
                            self.music_meter.get("active", False),
                            now - last_sample,
                        )
                        last_sample = now
                        self.music_meter.update(mood)
                        display(
                            {
                                "op": "music_pulse",
                                "expression": mood["expression"],
                                "level": self.music_meter.get("level", 0),
                                "active": self.music_meter.get("active", False),
                            }
                        )
                        self.closing.wait(0.2 if enabled else 1)
            except Exception:
                self.music_meter = {"active": False, "error": "Music microphone unavailable"}
                self.closing.wait(3)

    def deployments(self):
        return self.github_webhook.deployments(
            self.sources.state.get("deployments", [])
            if get_config()["notifications"].get("github_polling", True)
            else []
        )

    def poll_sources(self):
        while not self.closing.is_set():
            self.sources.poll()
            try:
                scene.set_deploying(bool(self.deployments()))
                self.sources.errors.pop("display", None)
            except Exception:
                self.sources.errors["display"] = "Deployment indicator unavailable"
            self.closing.wait(90)

    def deliver_notification(self):
        if self.notification_policy.snapshot()["snoozed"]:
            return
        if self.active_notification and time.time() < self.notification_until:
            return
        self.active_notification = None
        item = self.inbox.claim()
        if not item:
            return
        try:
            if not self.notification_policy.enabled_item(item):
                self.inbox.suppress(item["id"])
                return
            if item["priority"] == "low":
                self.inbox.finish(item["id"])
                return
            self.active_notification = item
            self.notification_until = time.time() + 15
            scene.present(item, 30 if item["priority"] in ("important", "urgent") else 15)
            audio_mode = self.notification_policy.audio(item)
            if audio_mode == "chime":
                from .chime import play

                self.announcing = True
                self.pi({"op": "ptt", "enabled": False})
                play()
            if audio_mode == "speech":
                self.announcing = True
                self.pi({"op": "ptt", "enabled": False})
                spoken = (item["title"] + ". " + item["body"])[:550]
                if item["source"] == "arrival":
                    from .welcome import message

                    composer = (
                        getattr(self.codex, "compose_welcome", None)
                        if get_config()["notifications"].get("generated_welcomes", True)
                        else None
                    )
                    spoken, generated = message(item, composer)
                    self.notify("welcome", {"generated": generated, "text": spoken})
                    scene.present(dict(item, body=spoken), 30)
                character_tools.speak(
                    spoken,
                    "happy" if item["source"] == "arrival" else "curious",
                    purpose="announcement",
                )
                scene.present(item, 5)
                self.notification_until = time.time() + 5
            self.inbox.finish(item["id"])
        except Exception as exc:
            self.inbox.finish(item["id"], str(exc)[:300])
            self.notify("error", {"message": "Notification delivery failed: " + str(exc)[:300]})
        finally:
            self.announcing = False

    def poll(self):
        last_error = None
        while not self.closing.is_set():
            try:
                busy = self.processing or self.announcing or (self.codex and self.codex.busy)
                armed = bool(
                    self.enabled
                    and not busy
                    and self.speech_health.get("available")
                    and (not self.codex or self.codex.process.poll() is None)
                )
                data = self.pi({"op": "ptt", "enabled": armed})
                self.device_health["voice"] = {"available": True, "error": None}
                if not busy and not data["recording"]:
                    self.status = (
                        "Paused"
                        if not self.enabled
                        else "Ready — hold the button to talk"
                        if armed
                        else "Voice backend unavailable — waiting for recovery"
                    )
                self.recording = data["recording"]
                if self.recording:
                    self.status = "Listening — release to send"
                    self.show_activity("listening")
                elif data.get("error") and data["error"] != last_error:
                    self.notify("error", {"message": data["error"]})
                    last_error = data["error"]
                clip = data.get("clip")
                if clip and not self.enabled:
                    self.pi({"op": "ptt", "enabled": False, "acknowledge": clip["clip_id"]})
                    clip = None
                if not clip and not busy and not self.recording:
                    self.deliver_notification()
                if clip and not busy:
                    self.processing = True
                    try:
                        # Freeze capture before a potentially long transcription.
                        self.pi({"op": "ptt", "enabled": False})
                        self.handle_clip(clip)
                    finally:
                        self.pi({"op": "ptt", "enabled": False, "acknowledge": clip["clip_id"]})
                        self.processing = False
                    if not self.codex or not self.codex.busy:
                        self.status = "Ready — hold the button to talk"
            except Exception:
                self.status = (
                    "Turn failed — ready for your next message"
                    if self.device_health["voice"]["available"]
                    else "Voice device unavailable — reconnecting"
                )
                self.closing.wait(3)
            self.closing.wait(0.4)

    def snapshot(self):
        with self.lock:
            approvals = []
            if self.codex:
                with self.codex.lock:
                    approvals = list(self.codex.approvals.values())
            return {
                "surfaces": self.surfaces.snapshot(),
                "spotify": self.media_source.status(),
                "media": self.media_source.status(),
                "music": dict(self.media_state.music),
                "tv": dict(self.media_state.video),
                "content_parse": dict(self.content_parse),
                "content_preview": self.content_preview.music() is not None,
                "music_mic": self.music_mic,
                "music_meter": dict(self.music_meter),
                "notifications": self.inbox.items(),
                "notification_policy": self.notification_policy.snapshot(),
                "focus": self.focus.status(),
                "agenda": agenda.snapshot(
                    self.sources.state, get_config()["notifications"]["agenda_timezone"]
                ),
                "active_notification": self.active_notification
                if time.time() < self.notification_until
                else None,
                "source_errors": dict(self.sources.errors),
                "github_queue_health": dict(self.github_queue.health)
                if self.github_queue
                else {"configured": False},
                "github_checks_health": dict(self.sources.state.get("github_checks_health", {})),
                "deployments": self.deployments(),
                "announcing": self.announcing,
                "timings": dict(self.timings),
                "recent_timings": timing.recent_turns(self.folder),
                "speech_timings": timing.read("speech"),
                "speech_engine": character_tools.speech.requested_engine(),
                "device_health": dict(self.device_health),
                "speech_health": dict(self.speech_health),
                "conversation_backend": get_config()["conversation"]["backend"],
                "codex_alive": self.codex is None or self.codex.process.poll() is None,
                "speaker_volume": dict(self.speaker_volume),
                "cloud_available": bool(os.getenv("OPENAI_API_KEY")),
                "status": self.status,
                "enabled": self.enabled,
                "recording": self.recording,
                "busy": bool(
                    self.processing or self.announcing or (self.codex and self.codex.busy)
                ),
                "thread_id": self.codex.thread_id if self.codex else None,
                "messages": list(self.messages),
                "approvals": approvals,
                "character": current_character()["name"],
                "profile": selection() or "configured",
                "style": current_character()["style"],
                "auto_approve_hardware": get_config()["approvals"]["auto_approve_hardware"],
            }

    def close(self):
        self.closing.set()
        try:
            self.pi({"op": "ptt", "enabled": False})
        except Exception:
            pass
        self.resources.close()


def handler(bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, value, content_type="application/json"):
            body = (
                value
                if isinstance(value, bytes)
                else value.encode()
                if isinstance(value, str)
                else json.dumps(value).encode()
            )
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            return self.headers.get("Host") in bridge.allowed_hosts and hmac.compare_digest(
                self.headers.get("X-Hardware-Token", ""), bridge.token
            )

        def do_GET(self):
            from .surface_http import handle

            if handle(self, bridge):
                return
            bridge.surfaces.observe(self.client_address[0], self.path)
            if self.path in ("/tv", "/tv/"):
                self.respond(
                    200,
                    (Path(__file__).parent / "web/tv.html").read_text(),
                    "text/html; charset=utf-8",
                )
            elif self.path in ("/tv.js", "/tv.css", "/lab-room.js"):
                self.respond(
                    200,
                    (Path(__file__).parent / "web" / self.path[1:]).read_text(),
                    "text/css" if self.path.endswith("css") else "application/javascript",
                )
            elif self.path in ("/surfaces/state", "/surfaces/assets"):
                token = self.headers.get("X-Surface-Token", "")
                if self.headers.get(
                    "Host"
                ) not in bridge.allowed_hosts or not bridge.surfaces.authorized(token):
                    self.respond(403, {"error": "Receiver session expired"})
                    return
                try:
                    if self.path.endswith("assets"):
                        self.respond(200, bridge.surfaces.character_assets(current_character()))
                    else:
                        self.respond(200, bridge.surfaces.view(token, bridge.snapshot()))
                except Exception:
                    self.respond(503, {"error": "Display unavailable; retrying"})
            elif self.path == "/":
                self.respond(
                    200,
                    (Path(__file__).parent / "web/index.html").read_text(),
                    "text/html; charset=utf-8",
                )
            elif self.path in ("/style.css", "/app.js", "/locations.js", "/dashboard-auth.js"):
                kind = "text/css" if self.path.endswith(".css") else "application/javascript"
                self.respond(200, (Path(__file__).parent / "web" / self.path[1:]).read_text(), kind)
            elif self.path in (
                "/okabe.png",
                "/kurisu.png",
                "/pip.png",
                "/sonic.png",
                "/github.png",
                "/calendar.png",
            ):
                self.respond(
                    200, (Path(__file__).parent / "web" / self.path[1:]).read_bytes(), "image/png"
                )
            elif self.path == "/content/crests" and self.authorized():
                self.respond(
                    200,
                    [],  # Crests are resolved on demand, not shipped as a registry.
                )
            elif self.path == "/content/presets" and self.authorized():
                self.respond(200, PRESETS)
            elif self.path == "/state" and self.authorized():
                self.respond(200, bridge.snapshot())
            else:
                self.respond(403, {"error": "Open the control URL printed by the bridge"})

        def do_POST(self):
            from .alexa_voice import handle as handle_alexa

            if handle_alexa(self, bridge):
                return
            from .surface_http import handle

            if handle(self, bridge, post=True):
                return
            bridge.surfaces.observe(self.client_address[0], self.path)
            if self.path in (
                "/surfaces/heartbeat",
                "/surfaces/ack",
                "/surfaces/return-receiver",
                "/surfaces/input",
                "/surfaces/closed",
            ):
                token = self.headers.get("X-Surface-Token", "")
                if self.headers.get(
                    "Host"
                ) not in bridge.allowed_hosts or not bridge.surfaces.authorized(
                    token, preview=False
                ):
                    self.respond(403, {"error": "Receiver session expired"})
                    return
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    if not 0 < n <= 1024:
                        raise ValueError("Invalid request size")
                    self.connection.settimeout(5)
                    data = json.loads(self.rfile.read(n))
                    if self.path.endswith("heartbeat"):
                        result = bridge.surfaces.heartbeat(token)
                    elif self.path.endswith("closed"):
                        result = bridge.surfaces.receiver_closed(token, data.get("transition_id"))
                    elif self.path.endswith("input"):
                        result = bridge.surfaces.input(token, data.get("key"))
                    elif self.path.endswith("ack"):
                        result = bridge.surfaces.acknowledge(
                            token, data.get("kind"), data.get("transition_id")
                        )
                    else:
                        result = bridge.surfaces.return_home()
                    self.respond(200, result)
                except Exception:
                    self.respond(400, {"error": "Invalid receiver command"})
                return
            if self.path == "/webhooks/github":
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    if not 0 < n <= 1_000_000:
                        raise ValueError("Invalid webhook size")
                    self.connection.settimeout(10)
                    result = bridge.github_webhook.receive(self.headers, self.rfile.read(n))
                    bridge.face_worker.submit(scene.set_deploying, bool(bridge.deployments()))
                    self.respond(200, result)
                except PermissionError:
                    self.respond(403, {"error": "Webhook forbidden"})
                except Exception:
                    self.respond(400, {"error": "Invalid webhook payload"})
                return
            if self.path == "/arrivals":
                if self.headers.get("Host") not in bridge.allowed_hosts or not hmac.compare_digest(
                    self.headers.get("X-Arrival-Token", ""), bridge.arrival_token
                ):
                    self.respond(403, {"error": "Forbidden"})
                    return
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    if not 0 < n <= 1024:
                        raise ValueError("Invalid arrival size")
                    self.connection.settimeout(10)
                    data = json.loads(self.rfile.read(n))
                    from .arrival import queue_greeting

                    item = queue_greeting(bridge.inbox, bridge.notification_policy, **data)
                    self.respond(200, {"queued": True, "id": item["id"]})
                except Exception:
                    self.respond(400, {"error": "Invalid or stale arrival event"})
                return
            if not self.authorized() and not may_publish(
                self.path,
                self.headers.get("Host"),
                bridge.allowed_hosts,
                self.headers.get("X-Notification-Token", ""),
                bridge.notification_token,
            ):
                self.respond(403, {"error": "Forbidden"})
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                if (
                    not 0
                    < n
                    <= (
                        950000
                        if self.path == "/conversation/test-clip"
                        else 350000
                        if self.path == "/audio/stream"
                        else 20000
                    )
                ):
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(n))
                if self.path == "/conversation/test-clip":
                    # Full dashboard authentication is required above; never accepts a
                    # publish-only token. Reuses the real clip ledger and transcription path.
                    import re

                    if set(data) != {"clip_id", "wav_base64"} or not re.fullmatch(
                        r"test-[A-Za-z0-9_-]{8,95}", data["clip_id"]
                    ):
                        raise ValueError("Use a unique test clip id and WAV data")
                    raw = base64.b64decode(data["wav_base64"], validate=True)
                    if len(raw) > 700000 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
                        raise ValueError("Invalid test WAV")
                    with bridge.lock:
                        if (
                            bridge.processing
                            or bridge.recording
                            or bridge.announcing
                            or not bridge.codex
                            or bridge.codex.busy
                        ):
                            raise ValueError("Wait until the current turn finishes")
                        bridge.processing = True

                    def inject():
                        try:
                            bridge.pi({"op": "ptt", "enabled": False})
                            bridge.handle_clip(dict(data, released_at=time.time()))
                        except Exception:
                            bridge.notify(
                                "error",
                                {"message": "Synthetic clip failed; check state before retrying"},
                            )
                        finally:
                            bridge.processing = False

                    threading.Thread(target=inject, daemon=True).start()
                    self.respond(202, {"accepted": True, "clip_id": data["clip_id"]})
                    return
                if self.path in bridge.application.ROUTES:
                    self.respond(200, bridge.application.execute(self.path, data))
                    return
                if self.path == "/content/preview":
                    self.respond(200, bridge.content_preview.start(data))
                    return
                if self.path == "/content/preview/stop":
                    bridge.content_preview.stop()
                    self.respond(200, {"preview": False})
                    return
                if self.path == "/content/context":
                    tv = dict(bridge.media_state.video)
                    if not tv.get("app") or not tv.get("content_id"):
                        self.respond(200, bridge.content_preview.start(data))
                        return
                    self.respond(
                        200, bridge.content_context.set(tv.get("app"), tv.get("content_id"), data)
                    )
                    return
                if self.path == "/music/microphone":
                    if type(data.get("enabled")) is not bool:
                        raise ValueError("enabled must be boolean")
                    bridge.music_mic = data["enabled"]
                    if not bridge.music_mic:
                        bridge.music_meter = bridge.pi({"op": "music_meter", "enabled": False})
                    self.respond(200, {"enabled": bridge.music_mic})
                    return
                if self.path in ("/media/connect", "/spotify/connect"):
                    self.respond(200, begin_auth(bridge.media_source))
                    return
                elif self.path == "/notifications":
                    self.respond(200, bridge.inbox.publish(**data))
                    return
                elif self.path == "/enabled":
                    if type(data.get("enabled")) is not bool:
                        raise ValueError("enabled must be boolean")
                    bridge.enabled = data["enabled"]
                    with tempfile.NamedTemporaryFile(mode="w", dir=state_dir(), delete=False) as f:
                        json.dump({"enabled": bridge.enabled}, f)
                        saved_button = Path(f.name)
                    saved_button.replace(state_dir() / "button-settings.json")
                    if not bridge.enabled:
                        bridge.pi({"op": "ptt", "enabled": False})
                    bridge.status = (
                        "Ready — hold the button to talk" if bridge.enabled else "Paused"
                    )
                elif self.path == "/speech-engine":
                    if (
                        bridge.announcing
                        or bridge.recording
                        or bridge.processing
                        or (bridge.codex and bridge.codex.busy)
                    ):
                        raise ValueError("Wait until the current turn finishes")
                    engine = data.get("engine")
                    if engine not in ("auto", "openai", "local"):
                        raise ValueError("Choose local or cloud speech")
                    if engine == "openai" and not os.getenv("OPENAI_API_KEY"):
                        raise ValueError("Configure OPENAI_API_KEY on the controller first")
                    path = state_dir() / "speech-settings.json"
                    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
                        json.dump({"engine": engine}, f)
                        tmp = Path(f.name)
                    tmp.replace(path)
                elif self.path == "/character":
                    if (
                        bridge.announcing
                        or bridge.recording
                        or bridge.processing
                        or (bridge.codex and bridge.codex.busy)
                    ):
                        raise ValueError("Wait until recording and the current turn finish")
                    # Disarm capture while changing the face and shared preference.
                    previous = bridge.enabled
                    bridge.enabled = False
                    try:
                        bridge.pi({"op": "ptt", "enabled": False})
                        profile = data.get("profile")
                        from .profiles import PROFILES

                        if not isinstance(profile, str) or (
                            profile not in PROFILES and profile != "configured"
                        ):
                            raise ValueError("Unknown character")
                        character = (
                            get_config()["character"]
                            if profile == "configured"
                            else {**get_config()["character"], **PROFILES[profile]}
                        )
                        scene_location = bridge.surfaces.snapshot()["current_location"]
                        if scene_location:
                            bridge.surfaces.ensure_scene(scene_location, character["style"])
                        character_tools.display_rpc(
                            {
                                "op": "character",
                                "activity": "idle",
                                "emotion": "neutral",
                                "style": character["style"],
                                "palette": character["palette"],
                            }
                        )
                        select_profile(profile)
                        bridge.speech_health = character_tools.speech.health()
                        bridge.face_activity = "idle"
                    finally:
                        bridge.enabled = previous
                elif self.path == "/answer" and bridge.codex:
                    bridge.codex.answer(
                        data["id"], data.get("decision"), data.get("answers"), data.get("persist")
                    )
                elif self.path == "/interrupt" and bridge.codex:
                    bridge.codex.interrupt()
                else:
                    raise ValueError("Unknown action")
                self.respond(200, {"ok": True})
            except Exception as exc:
                self.respond(400, {"error": str(exc)})

    return Handler


def main():
    parent_pid = os.environ.get("OKABEBOT_PARENT_PID")
    if parent_pid:

        def watch_parent():
            while os.getppid() == int(parent_pid):
                time.sleep(2)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=watch_parent, daemon=True).start()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Path to OkabeBot JSON configuration")
    parser.add_argument("--port", type=int)
    parser.add_argument("--transcribe-only", action="store_true")
    args = parser.parse_args()
    if args.config:
        os.environ["OKABEBOT_CONFIG"] = str(Path(args.config).expanduser().resolve())
        get_config.cache_clear()
    config = get_config()
    args.port = args.port or config["web"]["port"]
    folder = runtime_folder()
    # Refuse a second copy before touching the Pi or resuming the chat.
    import fcntl

    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    lockfile = (folder / "bridge.lock").open("w")
    fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Bind before initializing hardware, including copies using another state folder.
    server = ThreadingHTTPServer((config["web"]["host"], args.port), BaseHTTPRequestHandler)
    try:
        bridge = Bridge(args.port, args.transcribe_only)
        server.RequestHandlerClass = handler(bridge)
    except BaseException:
        server.server_close()
        raise
    loopback = None
    if config["web"]["host"] != "127.0.0.1":
        try:
            loopback = ThreadingHTTPServer(("127.0.0.1", args.port), handler(bridge))
            threading.Thread(target=loopback.serve_forever, daemon=True).start()
        except OSError:
            server.server_close()
            bridge.close()
            raise
    tls_server = None
    tls = config["web"]["tls"]
    if tls["certificate"]:
        import ssl

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(tls["certificate"], tls["key"])
        tls_server = ThreadingHTTPServer((config["web"]["host"], tls["port"]), handler(bridge))
        tls_server.socket = context.wrap_socket(tls_server.socket, server_side=True)
        bridge.allowed_hosts.update(
            h.rsplit(":", 1)[0] + ":" + str(tls["port"]) for h in list(bridge.allowed_hosts)
        )
        threading.Thread(target=tls_server.serve_forever, daemon=True).start()
    print("Control page: " + bridge.url, flush=True)

    def shutdown(*args):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if tls_server:
            tls_server.shutdown()
            tls_server.server_close()
        if loopback:
            loopback.shutdown()
            loopback.server_close()
        bridge.close()
        server.server_close()


if __name__ == "__main__":
    main()

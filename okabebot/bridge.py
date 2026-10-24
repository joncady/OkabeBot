"""Local push-to-talk control page, Whisper transcription, and Codex bridge."""

from contextlib import ExitStack
import argparse
import base64
import collections
import hmac
import json
import os
from pathlib import Path
import secrets
import signal
import sqlite3
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
        self.enabled = True
        self.closing = threading.Event()
        self.messages = collections.deque(maxlen=100)
        self.status = "Starting"
        self.face_worker = ThreadPoolExecutor(max_workers=1)
        self.resources.callback(self.face_worker.shutdown, wait=False, cancel_futures=True)
        self.face_activity = None
        self.recording = False
        self.processing = False
        self.codex = None
        self.token = secrets.token_urlsafe(32)
        self.port = port
        self.voice_rpc = self.resources.enter_context(device("voice").connect())
        self.pi({"op": "ptt", "enabled": False})
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            config["transcription"]["model"],
            device="cpu",
            compute_type=config["transcription"]["compute_type"],
            download_root=str(state_dir() / "models"),
            local_files_only=True,
        )
        if not transcribe_only:
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
        threading.Thread(target=self.poll, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%s/#%s" % (self.port, self.token)

    def pi(self, data):
        result = self.voice_rpc(data)
        if result.get("error") and "armed" not in result:
            raise RuntimeError(result["error"])
        return result

    def notify(self, kind, data):
        entry = {"kind": kind, "data": data, "time": time.time()}
        with self.lock:
            self.messages.append(entry)
            with (self.folder / "transcript.jsonl").open("a") as f:
                f.write(json.dumps(entry) + "\n")
            if kind == "error":
                self.status = str(data.get("message", data))
        print(kind, json.dumps(data)[:500], flush=True)

    def show_activity(self, activity):
        if self.face_activity == activity:
            return
        self.face_activity = activity
        self.face_worker.submit(
            character_tools.display_rpc,
            {
                "op": "character",
                "activity": activity,
                "palette": get_config()["character"]["palette"],
                "style": get_config()["character"]["style"],
            },
        )

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

    def transcribe(self, path):
        segments, _ = self.model.transcribe(
            str(path),
            language=get_config()["transcription"]["language"],
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(
            s.text.strip() for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1
        ).strip()

    def handle_clip(self, clip):
        clip_id = clip["clip_id"]
        with sqlite3.connect(self.folder / "clips.sqlite3") as db:
            if db.execute("SELECT 1 FROM clips WHERE id=?", (clip_id,)).fetchone():
                return
            # Claim before transcription/submission: never replay a command after a crash.
            db.execute("INSERT INTO clips VALUES (?, ?, ?)", (clip_id, "claimed", ""))
        self.status = "Transcribing"
        self.show_activity("thinking")
        raw = base64.b64decode(clip["wav_base64"], validate=True)
        if len(raw) > 700000:
            raise ValueError("Recording too large")
        with tempfile.TemporaryDirectory(prefix="hardware-ptt-") as tmp:
            path = Path(tmp) / "speech.wav"
            path.write_bytes(raw)
            text = self.transcribe(path)
        if not text:
            self.notify("notice", {"text": "No clear speech detected. Please try again."})
            return
        self.notify("user", {"text": text, "clip_id": clip_id})
        with sqlite3.connect(self.folder / "clips.sqlite3") as db:
            db.execute(
                "UPDATE clips SET status=?, transcript=? WHERE id=?", ("transcribed", text, clip_id)
            )
        if self.codex:
            self.status = "Codex is working"
            self.codex.submit(text)
            with sqlite3.connect(self.folder / "clips.sqlite3") as db:
                db.execute("UPDATE clips SET status=? WHERE id=?", ("submitted", clip_id))

    def poll(self):
        last_error = None
        while not self.closing.is_set():
            try:
                busy = self.processing or (self.codex and self.codex.busy)
                armed = bool(
                    self.enabled
                    and not busy
                    and (not self.codex or self.codex.process.poll() is None)
                )
                data = self.pi({"op": "ptt", "enabled": armed})
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
            except Exception as exc:
                self.enabled = False
                self.notify("error", {"message": str(exc)})
                self.closing.wait(3)
            self.closing.wait(0.4)

    def snapshot(self):
        with self.lock:
            approvals = []
            if self.codex:
                with self.codex.lock:
                    approvals = list(self.codex.approvals.values())
            return {
                "status": self.status,
                "enabled": self.enabled,
                "recording": self.recording,
                "busy": bool(self.processing or (self.codex and self.codex.busy)),
                "thread_id": self.codex.thread_id if self.codex else None,
                "messages": list(self.messages),
                "approvals": approvals,
                "character": get_config()["character"]["name"],
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
            body = value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            return self.headers.get("Host") == "127.0.0.1:%s" % bridge.port and hmac.compare_digest(
                self.headers.get("X-Hardware-Token", ""), bridge.token
            )

        def do_GET(self):
            if self.path == "/":
                self.respond(
                    200,
                    (Path(__file__).parent / "web/index.html").read_text(),
                    "text/html; charset=utf-8",
                )
            elif self.path in ("/style.css", "/app.js"):
                kind = "text/css" if self.path.endswith(".css") else "application/javascript"
                self.respond(200, (Path(__file__).parent / "web" / self.path[1:]).read_text(), kind)
            elif self.path == "/state" and self.authorized():
                self.respond(200, bridge.snapshot())
            else:
                self.respond(403, {"error": "Open the control URL printed by the bridge"})

        def do_POST(self):
            if not self.authorized():
                self.respond(403, {"error": "Forbidden"})
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                if not 0 < n <= 20000:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(n))
                if self.path == "/enabled":
                    if type(data.get("enabled")) is not bool:
                        raise ValueError("enabled must be boolean")
                    bridge.enabled = data["enabled"]
                    if not bridge.enabled:
                        bridge.pi({"op": "ptt", "enabled": False})
                    bridge.status = (
                        "Ready — hold the button to talk" if bridge.enabled else "Paused"
                    )
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
    bridge = Bridge(args.port, args.transcribe_only)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(bridge))
    except BaseException:
        bridge.close()
        raise
    print("Control page: " + bridge.url, flush=True)

    def shutdown(*args):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
        server.server_close()


if __name__ == "__main__":
    main()

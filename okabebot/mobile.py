"""Paired personal Android inbox and read-only context and preference conversation.

Firebase receives only opaque delivery IDs. Content, device credentials, chat and
speech stay on the controller. Push failures never replay speech or home actions.
"""

import base64
import json
import re
import sqlite3
import threading
import time
from pathlib import Path


class Mobile:
    def __init__(self, folder, registry, sender=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.folder / "mobile.sqlite3"
        self.registry = registry
        self.sender = sender or send_fcm
        self.external_sender = sender is not None
        self.lock = threading.RLock()
        self.chats = {}
        self.voice = {}
        self.voice_jobs = {}
        with self.db() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, token TEXT, enabled INTEGER);"
                "CREATE TABLE IF NOT EXISTS events (device TEXT, id TEXT, payload TEXT, created REAL, "
                "push_state TEXT, PRIMARY KEY(device,id));"
                "CREATE TABLE IF NOT EXISTS turns (device TEXT, id TEXT, created REAL, "
                "PRIMARY KEY(device,id));"
            )
        self.path.chmod(0o600)

    def db(self):
        return sqlite3.connect(self.path, timeout=5)

    def trace(self, identity, stage, error=None):
        with self.lock:
            now = time.monotonic()
            previous = self.voice.get(identity, {})
            if stage == "receiving":
                previous = {"started": now, "phase_started": now, "timings_s": {}}
            timings = dict(previous.get("timings_s", {}))
            old_stage = previous.get("stage")
            if old_stage and old_stage != stage and previous.get("phase_started"):
                timings[old_stage] = round(now - previous["phase_started"], 3)
            milestones = {
                k: previous[k]
                for k in ("first_pcm_s", "synthesis_first_pcm_s", "completion_s")
                if k in previous
            }
            if stage == "streaming" and "first_pcm_s" not in milestones:
                milestones["first_pcm_s"] = round(now - previous.get("started", now), 3)
                milestones["synthesis_first_pcm_s"] = timings.get("synthesizing", 0)
            if stage == "ready":
                milestones["completion_s"] = round(now - previous.get("started", now), 3)
            self.voice[identity] = {
                **milestones,
                "stage": stage,
                "at": time.time(),
                "error": error,
                "started": previous.get("started", now),
                "phase_started": now,
                "timings_s": timings,
                "server_total_s": round(now - previous.get("started", now), 3),
            }

    def voice_status(self, secret):
        item = self.device(secret)
        with self.lock:
            return {
                k: v
                for k, v in self.voice.get(item["id"], {"stage": "idle", "error": None}).items()
                if k not in ("started", "phase_started")
            }

    def voice_available(self, secret):
        identity = self.device(secret)["id"]
        with self.lock:
            if identity in self.voice_jobs:
                raise ValueError("Voice worker is busy; try a new recording after speech finishes")

    def cancel_voice_stream(self, identity):
        with self.lock:
            job = self.voice_jobs.get(identity)
            if job:
                job["stopped"].set()

    def start_voice_stream(self, secret, text, hub, surfaces):
        """Accept one private stream, then synthesize ahead of confirmed playback."""
        from . import speech
        from .character import current_voice
        from .profiles import current_character
        from .amadeus_text import TextConversation
        from .amadeus_habits import preference
        from .amadeus_onboarding import SYSTEM, KEY

        consent = TextConversation(self.folder.parent / "amadeus")
        item = self.device(secret)
        identity, style = item["id"], current_character()["style"]
        voice = current_voice()
        accepted, stopped, done = threading.Event(), threading.Event(), threading.Event()
        job = {"accepted": accepted, "stopped": stopped, "done": done}
        with self.lock:
            if identity in self.voice_jobs:
                raise ValueError("Voice worker is busy; try a new recording after speech finishes")
            self.voice_jobs[identity] = job
        with hub.condition:
            session = hub.receivers.get(identity, {}).get("session")

        def check():
            self.device(secret)
            with consent.store() as store:
                setup = preference(store, SYSTEM, KEY, {})
                settings = preference(
                    store, setup.get("profile", SYSTEM), "conversation.preferences", {}
                )
                if not consent.permitted(setup, {}) or settings.get("enabled") is not True:
                    raise PermissionError("Private conversation consent ended")
            if (
                stopped.is_set()
                or surfaces.phase != "tv"
                or surfaces.active_id != identity
                or current_character()["style"] != style
                or hub.receivers.get(identity, {}).get("session") != session
                or not hub.ready(identity)
            ):
                raise PermissionError("Private audio session ended")

        def abort():
            stopped.set()
            if job.get("stream_id"):
                try:
                    hub.command(identity, {"op": "stream_abort", "stream_id": job["stream_id"]})
                except ValueError:
                    pass

        def watch():
            while not done.wait(0.2):
                try:
                    check()
                except Exception:
                    abort()
                    return

        def produce():
            source = None
            try:
                with speech.synthesis_session():
                    check()
                    job["stream_id"] = hub.command(
                        identity, {"op": "stream_start", "startup_buffer_ms": 300}, check=check
                    )["stream_id"]
                    accepted.set()
                    threading.Thread(target=watch, daemon=True, name="mobile-stream-watch").start()
                    source = (
                        speech.local_pcm_chunks(text[:550], "neutral", voice, character=style)
                        if speech.engine() == "local"
                        else speech.pcm_chunks(text[:550], "neutral", voice)
                    )
                    total, sequence = 0, 0
                    for chunk in source:
                        check()
                        # Preserve producer boundaries, but cap transport events at 200 ms.
                        for offset in range(0, len(chunk), 9600):
                            check()
                            part = chunk[offset : offset + 9600]
                            if not part or len(part) % 2:
                                raise ValueError("Invalid private speech PCM")
                            total += len(part)
                            if total > 1440000:
                                raise ValueError("Private speech exceeds its duration bound")
                            hub.command(
                                identity,
                                {
                                    "op": "stream_chunk",
                                    "stream_id": job["stream_id"],
                                    "sequence": sequence,
                                    "pcm_base64": base64.b64encode(part).decode(),
                                },
                                check=check,
                            )
                            if sequence == 0:
                                self.trace(identity, "streaming")
                            sequence += 1
                    if not sequence:
                        raise ValueError("Speech provider returned no audio")
                    self.trace(identity, "draining")
                    hub.command(
                        identity, {"op": "stream_end", "stream_id": job["stream_id"]}, check=check
                    )
                    self.trace(identity, "ready")
            except Exception as exc:
                job["error"] = exc
                abort()
                self.trace(identity, "failed:streaming", type(exc).__name__)
            finally:
                if source is not None:
                    close = getattr(source, "close", None)
                    if close:
                        try:
                            close()
                        except Exception:
                            pass
                with self.lock:
                    self.voice_jobs.pop(identity, None)
                done.set()
                accepted.set()

        try:
            threading.Thread(target=produce, daemon=True, name="mobile-stream-producer").start()
        except Exception:
            with self.lock:
                self.voice_jobs.pop(identity, None)
            raise
        if not accepted.wait(3):
            abort()
            raise ValueError("Private speech acceptance timed out; no automatic retry")
        if "error" in job:
            raise job["error"]
        return {"playback_mode": "stream", "stream_id": job["stream_id"]}

    def run(self, closing):
        while not closing.wait(5):
            try:
                self.prune()
                self.flush()
            except Exception:
                pass

    def prune(self):
        known = set(self.registry.read()["devices"])
        with self.db() as db:
            db.execute("DELETE FROM events WHERE created<?", (time.time() - 7 * 86400,))
            db.execute("DELETE FROM turns WHERE created<?", (time.time() - 86400,))
            for (device,) in db.execute("SELECT id FROM devices").fetchall():
                if device not in known:
                    for table in ("devices", "events", "turns"):
                        column = "id" if table == "devices" else "device"
                        db.execute("DELETE FROM " + table + " WHERE " + column + "=?", (device,))

    def settings(self, update=None):
        if update is not None:
            if (
                not isinstance(update, dict)
                or set(update) != {"id", "enabled"}
                or type(update["enabled"]) is not bool
                or update["id"] not in self.registry.read()["devices"]
            ):
                raise ValueError("Choose a registered Android notification setting")
            with self.db() as db:
                if not db.execute("SELECT 1 FROM devices WHERE id=?", (update["id"],)).fetchone():
                    raise ValueError("Enable notifications on the Android app first")
                db.execute(
                    "UPDATE devices SET enabled=? WHERE id=?",
                    (int(update["enabled"]), update["id"]),
                )
        with self.db() as db:
            values = dict(db.execute("SELECT id,enabled FROM devices").fetchall())
        import os

        credential = self.folder / "firebase-service-account.local.json"
        return {
            "sender_configured": credential.is_file()
            or bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
            "devices": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "approved": p["approved"],
                    "registered": p["id"] in values,
                    "enabled": bool(values.get(p["id"])),
                    "last_voice": dict(self.voice.get(p["id"], {})),
                }
                for p in self.registry.read()["devices"].values()
                if p["adapter"] == "android"
            ],
        }

    def device(self, secret):
        item = self.registry.device(secret)
        if item["adapter"] != "android":
            raise PermissionError("Approve the Android screen first")
        return item

    def configure(self, secret, data):
        item = self.device(secret)
        if (
            not isinstance(data, dict)
            or set(data) - {"token", "enabled", "set_enabled"}
            or not {"token", "enabled"} <= set(data)
            or type(data["enabled"]) is not bool
            or type(data.get("set_enabled", False)) is not bool
            or not isinstance(data["token"], str)
            or not re.fullmatch(r"[A-Za-z0-9_:.-]{20,4096}", data["token"])
        ):
            raise ValueError("Provide a device messaging token and notification choice")
        with self.db() as db:
            previous = db.execute(
                "SELECT enabled FROM devices WHERE id=?", (item["id"],)
            ).fetchone()
            enabled = (
                data["enabled"]
                if previous is None or data.get("set_enabled")
                else bool(previous[0])
            )
            # A rotated/reinstalled app token must never fan out to an old identity.
            db.execute("DELETE FROM devices WHERE token=? AND id!=?", (data["token"], item["id"]))
            db.execute(
                "INSERT OR REPLACE INTO devices VALUES (?,?,?)",
                (item["id"], data["token"], int(enabled)),
            )
        return {"saved": True, "enabled": enabled}

    def inbox(self, secret):
        item = self.device(secret)
        with self.db() as db:
            rows = db.execute(
                "SELECT payload FROM events WHERE device=? AND created>? ORDER BY created DESC LIMIT 50",
                (item["id"], time.time() - 7 * 86400),
            ).fetchall()
        return {"items": [json.loads(row[0]) for row in rows]}

    def enqueue(self, item, device_id=None):
        """Called only after controller source/delivery policy permits a card."""
        public = {k: item[k] for k in ("id", "source", "title", "body", "priority")}
        self.prune()
        with self.db() as db:
            for (device,) in db.execute("SELECT id FROM devices WHERE enabled=1").fetchall():
                if device_id is not None and device != device_id:
                    continue
                current = self.registry.read()["devices"].get(device, {})
                if current.get("approved") and current.get("adapter") == "android":
                    db.execute(
                        "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",
                        (device, item["id"], json.dumps(public), time.time(), "pending"),
                    )

    def test(self, identity):
        import uuid

        device = next((p for p in self.settings()["devices"] if p["id"] == identity), None)
        if (
            not device
            or not device["approved"]
            or not device["registered"]
            or not device["enabled"]
        ):
            raise ValueError("Approve this phone and enable its notifications first")
        if not self.settings()["sender_configured"]:
            raise ValueError("Configure Firebase sender credentials first")
        self.enqueue(
            {
                "id": uuid.uuid4().hex,
                "source": "companion",
                "title": "Phone connection test",
                "body": "Your Amadeus inbox is connected.",
                "priority": "normal",
            },
            device_id=identity,
        )
        return {"queued": True, "delivery_confirmed": False}

    def flush(self):
        """One bounded attempt per event. Never sends personal content to Firebase."""
        if not self.external_sender and not self.settings()["sender_configured"]:
            return
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT e.device,e.id,d.token FROM events e JOIN devices d ON d.id=e.device "
                "WHERE e.push_state='pending' AND d.enabled=1 AND e.created>? LIMIT 10",
                (time.time() - 3600,),
            ).fetchall()
            for device, identity, _ in rows:
                db.execute(
                    "UPDATE events SET push_state='attempted' WHERE device=? AND id=?",
                    (device, identity),
                )
        for device, identity, token in rows:
            current = self.registry.read()["devices"].get(device, {})
            if not current.get("approved") or current.get("adapter") != "android":
                continue
            try:
                self.sender(token, identity)
            except Exception:
                # No token, provider response or private message in errors/logs.
                continue

    def chat(self, secret, data, generate, tool_turn=None, specs=None):
        item = self.device(secret)
        if (
            not isinstance(data, dict)
            or set(data) != {"text", "request_id"}
            or not isinstance(data["text"], str)
            or not 1 <= len(data["text"].strip()) <= 1000
            or not isinstance(data["request_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", data["request_id"])
        ):
            raise ValueError("Provide a short message and unique request ID")
        if generate is None:
            raise ValueError("Local conversation worker unavailable")
        # Claim before generation or memory writes: uncertain requests are never replayed.
        with self.db() as db:
            try:
                db.execute(
                    "INSERT INTO turns VALUES (?,?,?)",
                    (item["id"], data["request_id"], time.time()),
                )
            except sqlite3.IntegrityError:
                raise ValueError("Already submitted; no automatic retry") from None
        from .amadeus_text import TextConversation

        with self.lock:
            chat = self.chats.setdefault(
                item["id"],
                TextConversation(
                    self.folder.parent / "amadeus", state_key="conversation.mobile." + item["id"]
                ),
            )

        # The HTTP boundary supplies only a read-only tool callback.
        def guarded_generate(text, context):
            self.device(secret)
            result = generate(text, context)
            self.device(secret)
            return result

        def guarded_tools(text, **kwargs):
            self.device(secret)
            result = tool_turn(text, **kwargs)
            self.device(secret)
            return result

        result = chat.send(
            data["text"],
            guarded_generate,
            tool_turn=guarded_tools if tool_turn else None,
            specs=specs,
        )
        self.device(secret)  # Revocation during generation withholds the response.
        return result


def send_fcm(token, event_id):
    """Optional SDK; GOOGLE_APPLICATION_CREDENTIALS stays outside the repository."""
    import firebase_admin
    from firebase_admin import messaging

    try:
        app = firebase_admin.get_app("amadeus-mobile")
    except ValueError:
        from .config import state_dir
        from firebase_admin import credentials

        path = state_dir() / "mobile" / "firebase-service-account.local.json"
        credential = credentials.Certificate(str(path)) if path.is_file() else None
        app = firebase_admin.initialize_app(credential, {"httpTimeout": 10}, name="amadeus-mobile")
    messaging.send(
        messaging.Message(
            token=token,
            data={"event_id": event_id},
            notification=messaging.Notification(title="Amadeus", body="A new note is waiting."),
            android=messaging.AndroidConfig(
                priority="normal",
                ttl=3600,
                notification=messaging.AndroidNotification(
                    channel_id="amadeus_notes", tag=event_id
                ),
            ),
        ),
        app=app,
    )

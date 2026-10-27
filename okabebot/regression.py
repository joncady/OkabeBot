"""Opt-in local-model regressions: real inference, isolated actions, silent PCM checks."""

import argparse
import base64
import json
import math
from pathlib import Path
import shlex
import sqlite3
import statistics
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import uuid

from .application import Application
from .config import get_config
from .focus import FocusTimer
from .local_conversation import LocalConversation
from .notification_policy import NotificationPolicy
from .notifications import Inbox
from . import speech
from .audio_buffer import buffered_chunks


class Sandbox:
    """Real application/domain state, with deliberately simulated external devices."""

    def __init__(self, folder):
        self.calls = []
        self.volume = 20
        self.bot_ids = set()
        inbox = Inbox(folder)
        self.controller = SimpleNamespace(
            inbox=inbox,
            focus=FocusTimer(inbox),
            notification_policy=NotificationPolicy(folder),
            pi=self.pi,
            active_notification=None,
        )
        self.application = Application(self.controller)

    def pi(self, data):
        if data["op"] != "volume":
            raise ValueError("Only simulated mixer access is available")
        self.volume = data["percent"]
        return {"percent": self.volume}

    def execute(self, name, args):
        self.calls.append({"name": name, "arguments": dict(args), "at": time.monotonic()})
        routes = {
            "set_speaker_volume": "/speaker/volume",
            "control_focus_session": "/focus/" + args.get("action", ""),
            "snooze_notifications": "/notifications/snooze",
            "create_reminder": "/reminders/create",
            "cancel_reminder": "/reminders/cancel",
            "set_sender_notification_rule": "/notifications/senders",
            "set_notification_source": "/notifications/preferences",
        }
        if name == "set_notification_source":
            return self.application.execute(
                routes[name],
                {
                    "sources": {
                        args["source"]: {
                            "enabled": args.get("enabled", True),
                            "audio": args.get("audio", "default"),
                        }
                    }
                },
            )
        if name in routes:
            data = (
                {k: v for k, v in args.items() if k != "action"}
                if name == "control_focus_session"
                else args
            )
            return self.application.execute(routes[name], data)
        if name == "get_current_media":
            return {"tv": {"title": "Regression fixture"}, "music": {}}
        if name == "get_device_health":
            return {"device_health": {"voice": {"available": True}, "display": {"available": True}}}
        if name == "get_calendar_agenda":
            return {"available": True, "events": [{"title": "Fixture meeting", "start": "10:00"}]}
        if name == "get_focus_session":
            return self.controller.focus.status()
        if name == "press_bot":
            self.bot_ids.add(args["request_id"])
            return {"outcome": "confirmed", "simulated": True}
        if name == "control_spotify":
            return {"accepted": True, "simulated": True}
        if name == "speak_on_echo":
            return {"accepted": True, "playback_confirmed": False, "simulated": True}
        if name == "get_recent_notifications":
            return {"notifications": self.controller.inbox.items()}
        if name == "list_reminders":
            return {"reminders": []}
        if name in ("list_spotify_devices", "list_echo_speakers"):
            return {"devices": [], "speakers": []}
        if name == "get_bot_status":
            return {"battery": 100, "simulated": True}
        raise ValueError("Unsupported sandbox operation; no production fallback exists")


def check_pcm(text):
    import array

    first = None
    chunks = size = energy = 0
    started = time.monotonic()
    gaps = {}
    for data in buffered_chunks(speech.pcm_chunks(text, "neutral", "default"), metrics=gaps):
        if first is None:
            first = time.monotonic() - started
        values = array.array("h", data)
        energy += sum(v * v for v in values)
        size += len(data)
        chunks += 1
    seconds = size / 48000
    if not 0.15 <= seconds <= 30 or not energy or not chunks:
        raise ValueError("Missing, silent, truncated or excessive generated PCM")
    return {
        "first_buffered_pcm_s": round(first, 3),
        "generation_s": round(time.monotonic() - started, 3),
        "audio_s": round(seconds, 3),
        "rms": round(math.sqrt(energy / (size / 2)), 1),
        "chunks": chunks,
        **gaps,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--speech",
        action="store_true",
        help="Generate and inspect actual voice-worker PCM; never plays it",
    )
    parser.add_argument(
        "--audio",
        action="store_true",
        help="Generate synthetic WAV via macOS say and run actual Whisper/clip handling",
    )
    parser.add_argument("--case", action="append", help="Run selected fixture IDs")
    parser.add_argument(
        "--max-action-seconds", type=float, help="Optional warm routing+dispatch regression budget"
    )
    parser.add_argument("--worker-command", help="Override worker argv for an isolated comparison")
    parser.add_argument("--model", help="Override model for an isolated comparison")
    args = parser.parse_args(argv)
    cases = json.loads(args.fixtures.read_text())
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    if not cases:
        parser.error("No matching cases")
    if not get_config()["conversation"]["command"]:
        parser.error("Configure a local worker command first")
    rows = []
    generation = []
    with tempfile.TemporaryDirectory(prefix="okabebot-regression-") as temp:
        folder = Path(temp)
        sandbox = Sandbox(folder)
        events = []
        answers = []
        done = threading.Event()

        def notify(kind, data):
            events.append((kind, data))
            if kind == "turn_completed":
                done.set()

        def completed(text, status):
            answers.append(text)

        class RecordingLocalConversation(LocalConversation):
            def _read(self, timeout=45):
                result = super()._read(timeout)
                if "text" in result:
                    self.last_output = result["text"]
                return result

        settings = dict(get_config()["conversation"])
        if args.worker_command:
            settings["command"] = shlex.split(args.worker_command)
        if args.model:
            settings["model"] = args.model
        adapter = RecordingLocalConversation(
            folder, notify, completed, executor=sandbox.execute, settings=settings
        )
        bridge = None
        try:
            if args.audio:
                from faster_whisper import WhisperModel
                from .bridge import Bridge

                bridge = Bridge.__new__(Bridge)
                bridge.folder = folder
                bridge.codex = adapter
                bridge.notify = notify
                bridge.show_activity = lambda *a: None
                cfg = get_config()["transcription"]
                bridge.model = WhisperModel(
                    cfg["model"], device="cpu", compute_type=cfg["compute_type"]
                )
                with sqlite3.connect(folder / "clips.sqlite3") as db:
                    db.execute(
                        "CREATE TABLE clips (id TEXT PRIMARY KEY,status TEXT,transcript TEXT)"
                    )
            for case in cases:
                events.clear()
                answers.clear()
                done.clear()
                sandbox.calls.clear()
                adapter.last_output = None
                row = {"id": case["id"], "input": case["text"]}
                started = time.monotonic()
                if bridge:
                    source = folder / "source.aiff"
                    wav = folder / "input.wav"
                    subprocess.run(
                        ["say", "-v", "Samantha", "-o", str(source), case["text"]],
                        check=True,
                        capture_output=True,
                    )
                    speech.normalize(source, wav)
                    started = time.monotonic()
                    bridge.handle_clip(
                        {
                            "clip_id": "regression-" + uuid.uuid4().hex,
                            "released_at": time.time(),
                            "wav_base64": base64.b64encode(wav.read_bytes()).decode(),
                        }
                    )
                else:
                    adapter.submit(case["text"])
                if not done.wait(60):
                    raise TimeoutError("Regression turn timed out; no retry")
                calls = sandbox.calls.copy()
                expected = case["tool"]
                passed = (
                    (
                        len(calls) == 1
                        and calls[0]["name"] == expected
                        and all(
                            calls[0]["arguments"].get(k) == v
                            for k, v in case.get("args", {}).items()
                        )
                    )
                    if expected
                    else not calls
                )
                if any(k == "error" for k, d in events):
                    passed = False
                elapsed = time.monotonic() - started
                row.update(
                    passed=passed,
                    elapsed_s=round(elapsed, 3),
                    calls=[{k: v for k, v in c.items() if k != "at"} for c in calls],
                    answer=answers[-1] if answers else "",
                    model_output=getattr(adapter, "last_output", None),
                    metrics=[d for k, d in events if k == "local_model"],
                )
                if calls:
                    row["action_s"] = round(calls[0]["at"] - started, 3)
                    generation.append(row["action_s"])
                    if args.max_action_seconds and row["action_s"] > args.max_action_seconds:
                        row["passed"] = False
                if bridge:
                    row["transcript"] = next((d["text"] for k, d in events if k == "user"), None)
                    row["transcription_s"] = bridge.timings.get("transcription_s")
                if args.speech and answers:
                    try:
                        row["speech"] = check_pcm(answers[-1][:500])
                    except Exception as exc:
                        row.update(passed=False, speech_error=str(exc))
                rows.append(row)
                print(json.dumps(row), flush=True)
        finally:
            adapter.close()
    report = {
        "cases": rows,
        "passed": sum(r["passed"] for r in rows),
        "total": len(rows),
        "median_action_s": round(statistics.median(generation), 3) if generation else None,
        "notes": "Actual local model, optional actual Whisper and silent TTS PCM. All action dispatch uses isolated state and simulated hardware. No production state, Pi speaker, SwitchBot, Spotify or Echo calls. Latency excludes physical capture/upload and model startup.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    return 0 if report["passed"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

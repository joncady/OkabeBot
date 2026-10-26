"""Local conversation adapter with schema validation and explicit action grounding."""

import asyncio
import copy
import json
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from jsonschema import Draft202012Validator
from .config import get_config
from .profiles import current_character

READ_TOOLS = {
    "get_current_media",
    "get_device_health",
    "get_calendar_agenda",
    "get_focus_session",
    "get_recent_notifications",
    "list_reminders",
    "list_spotify_devices",
    "list_echo_speakers",
    "get_bot_status",
}
TARGETS = {
    "set_speaker_volume": r"\b(volume|speaker|mute)\b",
    "control_focus_session": r"\b(focus|timer)\b",
    "control_spotify": r"\bspotify\b",
    "press_bot": r"\b(switch\s*bot|wave)\b",
    "speak_on_echo": r"\b(echo|show|sonos)\b",
    "snooze_notifications": r"\b(alerts?|notifications?)\b",
    "dismiss_notification": r"\b(alerts?|notifications?|cards?)\b",
    "create_reminder": r"\b(remind|reminder)\b",
    "cancel_reminder": r"\breminders?\b",
    "show_calendar_agenda": r"\b(calendar|agenda|schedule)\b",
}


def validate_call(text, call, specs, policy, request_id):
    name, args = call.get("name"), call.get("arguments", {})
    if name not in specs or not isinstance(args, dict):
        raise ValueError("That command is not available locally. Could you be more specific?")
    args = dict(args)
    if name in ("press_bot", "create_reminder"):
        args["request_id"] = request_id
    schema = specs[name]["parameters"]
    if set(args) - set(schema.get("properties", {})):
        raise ValueError("I could not validate that command. Please try a more explicit request.")
    try:
        Draft202012Validator(schema).validate(args)
    except Exception:
        raise ValueError("I need more precise details for that command.") from None
    if name not in READ_TOOLS:
        if not policy["auto_approve_hardware"] or name not in policy["allowed_tools"]:
            raise ValueError("That action is not enabled in the local tool approval configuration.")
        if (
            not re.search(TARGETS[name], text, re.I)
            or re.search(r"\b(don['’]t|do not|never)\b", text, re.I)
            or re.match(r"\s*(what|why|how|explain|describe)\b", text, re.I)
        ):
            raise ValueError("Which device or action do you mean? Please name it explicitly.")
        if name == "set_speaker_volume":
            if not re.search(
                r"\b(set|turn|lower|raise|reduce|increase|mute|unmute|make)\b", text, re.I
            ):
                raise ValueError(
                    "Would you like to change the speaker volume? Please say the percentage."
                )
            numbers = re.findall(r"(\d+)\s*(?:%|percent)", text, re.I)
            if not numbers:
                numbers = re.findall(r"\b\d+\b", text)
            if not numbers:
                words = {
                    "zero": 0,
                    "one": 1,
                    "two": 2,
                    "three": 3,
                    "four": 4,
                    "five": 5,
                    "six": 6,
                    "seven": 7,
                    "eight": 8,
                    "nine": 9,
                    "ten": 10,
                    "eleven": 11,
                    "twelve": 12,
                    "thirteen": 13,
                    "fourteen": 14,
                    "fifteen": 15,
                    "sixteen": 16,
                    "seventeen": 17,
                    "eighteen": 18,
                    "nineteen": 19,
                    "twenty": 20,
                    "thirty": 30,
                    "forty": 40,
                    "fifty": 50,
                    "sixty": 60,
                    "seventy": 70,
                    "eighty": 80,
                    "ninety": 90,
                    "hundred": 100,
                }
                tokens = re.findall(r"[a-z]+", text.lower())
                values = [words[w] for w in tokens if w in words]
                if values:
                    numbers = [str(100 if values == [1, 100] else sum(values))]
            if (
                not numbers
                and re.search(r"\bmute\b", text, re.I)
                and not re.search(r"\bunmute\b", text, re.I)
            ):
                numbers = ["0"]
            if len(set(numbers)) != 1 or str(args["percent"]) != numbers[0]:
                raise ValueError("Please state the exact speaker volume percentage.")
    return name, args


def acknowledgement(name, result):
    if isinstance(result, dict) and result.get("error"):
        return "The request failed. Please check the dashboard before trying again."
    if name == "set_speaker_volume":
        return "Speaker volume is now %s percent." % result["percent"]
    if name == "press_bot":
        return (
            "The SwitchBot acknowledged the press."
            if result.get("outcome") == "confirmed"
            else "The SwitchBot request returned. Check the device before trying again."
        )
    if name == "control_focus_session":
        return "Focus timer started." if result.get("active") else "Focus timer cancelled."
    if name == "control_spotify":
        return "Spotify accepted the request. Playback is not independently confirmed."
    if name == "speak_on_echo":
        return "The message was sent to the selected Echo."
    if name == "snooze_notifications":
        return "Notification preferences updated."
    if name == "dismiss_notification":
        return "Notification dismissed."
    if name == "create_reminder":
        return "Your reminder is scheduled."
    if name == "cancel_reminder":
        return (
            "Reminder cancelled."
            if result.get("cancelled")
            else "That pending reminder was not found."
        )
    if name == "show_calendar_agenda":
        return "The agenda card is queued on the screen."
    if name == "get_device_health":
        items = result.get("device_health", {})
        return (
            " ".join(
                k + (" is connected." if v.get("available") else " is unavailable.")
                for k, v in items.items()
            )
            or "Device health is unavailable."
        )
    if name == "get_current_media":
        tv, music = result.get("tv") or {}, result.get("music") or {}
        title = tv.get("title") or music.get("title") or music.get("track")
        return (
            ("Current media: " + str(title)[:180] + ".")
            if title
            else "No media title is currently available."
        )
    if name == "get_calendar_agenda":
        if not result.get("available"):
            return "Calendar data is unavailable or stale."
        events = result.get("events", [])
        return (
            ("Calendar: " + "; ".join(str(e["start"]) + " " + e["title"] for e in events[:3]))[:500]
            if events
            else "No events were found in that calendar view."
        )
    if name == "get_focus_session":
        return "A focus timer is active." if result.get("active") else "No focus timer is active."
    if name in ("list_spotify_devices", "list_echo_speakers"):
        values = result.get("devices", result.get("speakers", []))
        return (
            "Available destinations: "
            + (
                ", ".join(v.get("name", "unnamed") if isinstance(v, dict) else v for v in values)
                or "none currently available"
            )
            + "."
        )
    if name == "get_bot_status":
        return "SwitchBot status was retrieved. Details are on the dashboard."
    rows = result.get("notifications", result.get("reminders", []))
    return (
        ("Recent items: " + "; ".join(r.get("title", r.get("body", "")) for r in rows[:3]))[:500]
        if rows
        else "No matching recent items were found."
    )


class LocalConversation:
    label = "Local model"

    def __init__(self, folder, notify, completed):
        from . import server

        self.notify, self.completed = notify, completed
        self.lock = threading.RLock()
        self.approvals = {}
        self.busy = False
        self.thread_id = "local-conversation"
        self.cancelled = threading.Event()
        self.closed = False
        self.settings = get_config()["conversation"]
        self.policy = get_config()["approvals"]
        allowed = READ_TOOLS | set(TARGETS)

        async def tools():
            return await server.mcp.list_tools()

        self.specs = {
            t.name: {
                "name": t.name,
                "description": t.description.split("\n")[0][:160],
                "parameters": t.inputSchema,
            }
            for t in asyncio.run(tools())
            if t.name in allowed
        }
        worker_specs = copy.deepcopy(self.specs)
        for name in ("press_bot", "create_reminder"):
            worker_specs[name]["parameters"]["properties"].pop("request_id", None)
            required = worker_specs[name]["parameters"].get("required", [])
            worker_specs[name]["parameters"]["required"] = [
                k for k in required if k != "request_id"
            ]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
        self.log = (Path(folder) / "local-model.log").open("a")
        self.process = subprocess.Popen(
            self.settings["command"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            bufsize=1,
            env=env,
        )
        self.lines = queue.Queue()

        def read():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)

        threading.Thread(target=read, daemon=True).start()
        self.process.stdin.write(
            json.dumps(
                {
                    "model": self.settings["model"],
                    "tools": [{"type": "function", "function": s} for s in worker_specs.values()],
                }
            )
            + "\n"
        )
        self.process.stdin.flush()
        try:
            if not self._read(120).get("ready"):
                raise RuntimeError("Local worker not ready")
        except Exception:
            self.close()
            raise
        try:
            self.process.stdin.write(
                json.dumps(
                    {"text": "Hello.", "persona": current_character()["persona"], "warmup": True}
                )
                + "\n"
            )
            self.process.stdin.flush()
            if self._read(120).get("error"):
                raise RuntimeError("Local warmup failed")
        except Exception:
            self.close()
            raise
        self.notify("connected", {"thread_id": self.thread_id, "backend": "local"})

    def _read(self, timeout=45):
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            self.process.terminate()
            raise RuntimeError("Local model timed out; no action was retried") from None
        if line is None:
            raise RuntimeError("Local model disconnected; restart the controller")
        return json.loads(line)

    def submit(self, text):
        with self.lock:
            if self.busy:
                raise ValueError("A local turn is already running")
            self.busy = True
            self.cancelled.clear()
        threading.Thread(target=self._turn, args=(text,), daemon=True).start()

    def _turn(self, text):
        from . import server

        status = "completed"
        try:
            self.process.stdin.write(
                json.dumps({"text": text[:2000], "persona": current_character()["persona"]}) + "\n"
            )
            self.process.stdin.flush()
            result = self._read()
            if result.get("error"):
                raise RuntimeError("Local generation failed; no action executed")
            if self.cancelled.is_set():
                return
            self.notify(
                "local_model",
                {
                    k: result[k]
                    for k in ("selection_s", "prompt_tokens", "generated_tokens")
                    if k in result
                },
            )
            output = result["text"].strip()
            matches = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", output, re.S)
            if matches:
                if len(matches) != 1 or output.count("<tool_call>") != 1:
                    raise ValueError("Please ask for one action at a time.")
                try:
                    call = json.loads(matches[0])
                except ValueError:
                    raise ValueError(
                        "I could not validate the command. Please repeat it explicitly."
                    ) from None
                name, args = validate_call(
                    text, call, self.specs, self.policy, "local-" + uuid.uuid4().hex
                )
                if self.cancelled.is_set():
                    return
                self.notify("local_tool", {"tool": name, "selection_s": result["selection_s"]})
                tool_started = time.monotonic()
                actual = getattr(server, name)(**args)
                self.notify(
                    "local_execution",
                    {"tool": name, "duration_s": round(time.monotonic() - tool_started, 3)},
                )
                output = acknowledgement(name, actual)
            elif output.startswith("{"):
                try:
                    output = json.loads(output).get("clarify", "Please name the device and action.")
                except ValueError:
                    output = "Please name the device and action."
            if not matches and re.search(
                r"\b(set|turn|press|wave|pause|start|cancel|snooze|dismiss|remind|show|play|mute)\b",
                text,
                re.I,
            ):
                output = "Which device and action do you mean?"
            self.notify("assistant", {"text": output[:550], "phase": "final_answer"})
            if not self.cancelled.is_set():
                self.completed(output[:550], status)
        except ValueError as exc:
            if not self.cancelled.is_set():
                self.notify("assistant", {"text": str(exc), "phase": "final_answer"})
                self.completed(str(exc)[:400], status)
        except Exception:
            status = "failed"
            self.notify(
                "error",
                {
                    "message": "Local turn failed or outcome uncertain. Check the device before retrying."
                },
            )
        finally:
            with self.lock:
                self.busy = False
            self.notify(
                "turn_completed",
                {"status": "cancelled" if self.cancelled.is_set() else status, "error": None},
            )

    def interrupt(self):
        self.cancelled.set()

    def answer(self, *args):
        raise ValueError("Local mode has no pending approval forms")

    def close(self):
        self.closed = True
        self.cancelled.set()
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.log.close()

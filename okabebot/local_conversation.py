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
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from jsonschema import Draft202012Validator
from .config import get_config
from .profiles import current_character
from . import locations

READ_TOOLS = {
    "get_companion_locations",
    "get_current_media",
    "get_device_health",
    "get_calendar_agenda",
    "get_focus_session",
    "get_home_activity",
    "get_presence_history",
    "get_chores",
    "get_context_feed",
    "get_trakt_watchlist",
    "get_watch_recommendations",
    "get_proactive_explanation",
    "get_personal_recommendation_context",
    "get_recent_notifications",
    "list_reminders",
    "list_spotify_devices",
    "list_echo_speakers",
    "get_bot_status",
}
TARGETS = {
    "move_companion": locations.MOVE_VERB,
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
    "set_notification_source": r"\b(alerts?|notifications?)\b",
    "set_sender_notification_rule": r"\b(alerts?|notifications?|sender)\b",
}


DOMAINS = (
    (
        r"\b(tasks?|to.?do|(?:alexa|shopping|task)\s+lists?|appliances?|laundry|transit|watch(?:ed)? history)\b",
        {"get_context_feed"},
    ),
    (r"\b(volume|speaker|mute|unmute)\b", {"set_speaker_volume", "get_device_health"}),
    (r"\b(spotify)\b", {"control_spotify", "get_current_media", "list_spotify_devices"}),
    (r"\b(tv|television|playing|music|video|song|watching)\b", {"get_current_media"}),
    (r"\b(switch\s*bot|wave)\b", {"press_bot", "get_bot_status"}),
    (r"\b(focus|timer)\b", {"control_focus_session", "get_focus_session"}),
    (r"\b(remind|reminders?)\b", {"create_reminder", "cancel_reminder", "list_reminders"}),
    (
        r"\b(calendar|agenda|schedule|appointments?)\b",
        {"get_calendar_agenda", "show_calendar_agenda"},
    ),
    (
        r"\b(alerts?|notifications?|inbox|missed)\b",
        {
            "get_recent_notifications",
            "snooze_notifications",
            "dismiss_notification",
            "set_notification_source",
            "set_sender_notification_rule",
        },
    ),
    (r"\b(echo|sonos)\b|\bon\s+show\b", {"speak_on_echo", "list_echo_speakers"}),
    (r"\b(connected|online|health|devices?|working)\b", {"get_device_health"}),
)
NEGATED = r"\b(don['’]t|do not|never|shouldn['’]t|wouldn['’]t|without|no need to|not now)\b"
HYPOTHETICAL = r"\b(hypothetically|suppose|pretend|imagine|explain|describe|would happen)\b"


def household_request(text):
    return bool(
        re.search(r"\b(house|home|apartment|household)\b", text, re.I)
        and re.search(
            r"\b(happen(?:ed|ing)?|miss(?:ed)?|activity|updates?|status|anything|going on)\b",
            text,
            re.I,
        )
    )


def shortlist(text, available):
    from .turn_resolution import operational_text

    raw_text, text = text, operational_text(text)
    if re.search(
        r"\b(?:when|what time) did I (?:leave|return|arrive)|\bdid I\b.*\b(?:away|not home)\b|\bpresence history\b",
        text,
        re.I,
    ):
        return ["get_presence_history"] if "get_presence_history" in available else []
    if household_request(text):
        return ["get_home_activity"] if "get_home_activity" in available else []
    if (
        re.search(locations.MOVE_VERB, text, re.I)
        and locations.movement_request(raw_text)
        and "move_companion" in available
    ):
        return ["move_companion"]
    if re.search(
        r"\b(where am i|(?:which|what) room am i in|(?:last|recent) nfc (?:scan|room))\b",
        text,
        re.I,
    ):
        return ["get_companion_locations"] if "get_companion_locations" in available else []
    if re.search(
        r"\b(where|which|what)\b.*\b(locations?|destinations?|screens?|you.*go|you.*are|are you)\b",
        text,
        re.I,
    ):
        return ["get_companion_locations"] if "get_companion_locations" in available else []
    names = set()
    for pattern, candidates in DOMAINS:
        if re.search(pattern, text, re.I):
            names.update(candidates)
    question = bool(re.match(r"\s*(what|which|is|are|how|why)\b", text, re.I))
    # Explicit verbs narrow the domain, but never add a tool absent from that domain.
    choices = (
        ("control_spotify", r"\b(play|resume|pause|stop|skip|next|previous)\b"),
        ("control_focus_session", r"\b(start|begin|set|cancel|stop|end|give)\b"),
        ("set_speaker_volume", r"\b(set|turn|lower|raise|reduce|increase|mute|unmute)\b"),
        ("press_bot", r"\b(press|wave)\b"),
        ("speak_on_echo", r"\b(say|speak|tell|announce)\b"),
        ("snooze_notifications", r"\b(snooze|hold|pause|resume|let)\b"),
        ("create_reminder", r"\bremind\b"),
        ("cancel_reminder", r"\b(cancel|delete)\b"),
        ("show_calendar_agenda", r"\bshow\b"),
    )
    if not question:
        for name, pattern in choices:
            if name in names and re.search(pattern, text, re.I):
                return [name] if name in available else []
    if question:
        names -= set(TARGETS)
    return sorted(names & set(available))


def preference_device_request(text, specs):
    """Interest words such as watching/gaming must not hijack preference replies."""
    if not shortlist(text, specs):
        return False
    return bool(
        locations.movement_request(text)
        or household_request(text)
        or re.match(
            r"\s*(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?(?:check|tell|turn|set|play|pause|stop|start|cancel|show|press|wave|mute|unmute|remind|snooze|dismiss|what|where|which|is|are|how)\b",
            text,
            re.I,
        )
    )


def preflight(text):
    from .turn_resolution import operational_text

    text = operational_text(text)
    if re.search(locations.MOVE_VERB, text, re.I) and (
        re.search(NEGATED, text, re.I) or re.search(HYPOTHETICAL, text, re.I)
    ):
        return "I haven't moved anywhere."
    if re.search(r"\bturn\s+(it|that|this)\s+(on|off)\b", text, re.I):
        return "Which device do you mean?"
    if re.search(
        r"\b(and|then|also)\b.*\b(set|turn|pause|play|press|wave|start|cancel|mute|snooze)\b",
        text,
        re.I,
    ):
        return "Please ask for one action at a time."
    if re.search(
        r"\b(set|turn|press|wave|pause|start|cancel|snooze|dismiss|play|mute)\b", text, re.I
    ) and (re.search(NEGATED, text, re.I) or re.search(HYPOTHETICAL, text, re.I)):
        return "I haven't changed anything."
    return None


def validate_call(text, call, specs, policy, request_id, resolved_device_id=""):
    if not isinstance(call, dict):
        raise ValueError("I need one valid tool request.")
    if preflight(text):
        raise ValueError(preflight(text))
    name, args = call.get("name"), call.get("arguments", {})
    if (
        name not in specs
        or (name not in READ_TOOLS and name not in shortlist(text, specs))
        or not isinstance(args, dict)
    ):
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
        from .turn_resolution import assert_action_request, operational_text

        assert_action_request(text, name)
        if not policy["auto_approve_hardware"] or name not in policy["allowed_tools"]:
            raise ValueError("That action is not enabled in the local tool approval configuration.")
        if (
            not re.search(TARGETS[name], text, re.I)
            or re.search(r"\b(don['’]t|do not|never)\b", operational_text(text), re.I)
            or re.match(r"\s*(what|why|how|explain|describe)\b", text, re.I)
        ):
            raise ValueError("Which device or action do you mean? Please name it explicitly.")
        if name == "move_companion":
            if locations.destination(text) != args.get("location_id"):
                raise ValueError("Please name one configured destination explicitly.")
        if name == "control_spotify":
            if (
                args.get("device_id")
                and args["device_id"] not in text
                and args["device_id"] != resolved_device_id
            ):
                raise ValueError(
                    "Name a currently discovered Spotify device; I won't guess its ID."
                )
            if args.get("uri") and args["uri"] not in text:
                raise ValueError("Please provide an exact Spotify URI, or ask to resume playback.")
            verbs = {
                "play": r"\b(play|resume|start)\b",
                "pause": r"\b(pause|stop)\b",
                "next": r"\b(next|skip)\b",
                "previous": r"\b(previous|back)\b",
            }
            if not re.search(verbs[args["action"]], text, re.I):
                raise ValueError("Please state the Spotify action explicitly.")
        if name == "control_focus_session":
            pattern = (
                r"\b(cancel|stop|end)\b"
                if args["action"] == "cancel"
                else r"\b(start|begin|set|give)\b"
            )
            if not re.search(pattern, text, re.I):
                raise ValueError("Please state the timer action explicitly.")
        if name == "snooze_notifications":
            from .turn_resolution import notification_pause

            pause = notification_pause(text)
            if pause:
                args = pause["arguments"]
        if name in ("set_notification_source", "set_sender_notification_rule"):
            from .turn_resolution import notification_arguments

            args = notification_arguments(text, name, args)
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


def parse_tool_call(output):
    """Accept one complete native call; some tokenizers omit the closing stop token."""
    value = output.strip()
    native = value.startswith("<tool_call>")
    if native:
        if value.count("<tool_call>") != 1:
            raise ValueError("Please ask for one action at a time.")
        value = value[len("<tool_call>") :].strip()
        if value.endswith("</tool_call>"):
            value = value[: -len("</tool_call>")].strip()
    elif "<tool_call>" in value:
        raise ValueError("I could not validate one tool request.")
    if native or value.startswith("{"):
        try:
            obj = json.loads(value)
        except ValueError:
            raise ValueError(
                "I could not validate the command. Please repeat it explicitly."
            ) from None
        if not isinstance(obj, dict):
            raise ValueError("I need one valid tool request.")
        if "name" in obj:
            if set(obj) != {"name", "arguments"}:
                raise ValueError("Unexpected tool request fields.")
            return obj
        if native:
            raise ValueError("Missing tool name.")
    return None


def acknowledgement(name, result):
    if isinstance(result, dict) and result.get("error"):
        return "The request failed. Please check the dashboard before trying again."
    if name == "get_presence_history":
        if not result.get("available"):
            return "Selected presence history isn't available. Check its connection and private source selections."
        changes = [r for r in result.get("transitions", []) if r.get("observation") == "change"]
        people = [
            r for r in changes if r.get("source_type") == "person" and r.get("state") == "away"
        ]
        if people:
            return (
                "The selected person reported away at "
                + people[0]["at"]
                + ". That's a presence report, not proof of departure."
            )
        return "I don't have a reported person departure in this window. Zone counts and missing reports can't establish when you left."
    if name == "get_personal_recommendation_context":
        if result.get("state"):
            return "Your private recommendation context isn't available right now."
        preferences = result.get("preferences", {})
        if not preferences:
            return "I don't have saved preferences for that yet. What would you like an idea for?"
        values = [v for rows in preferences.values() for v in rows]
        return (
            "Your saved preferences include "
            + ", ".join(values)[:250]
            + ". I haven't checked your time, energy or supplies."
        )
    if name == "move_companion":
        return (
            ("I'm already at " if result.get("already_there") else "Heading to ")
            + result["destination_name"]
            + "."
        )
    if name == "get_proactive_explanation":
        return result.get("suggestion", {}).get(
            "reason", "I don't have a delivery receipt explaining that suggestion."
        )
    if name == "get_watch_recommendations":
        from .watch_recommendations import fallback

        return fallback(result)
    if name == "get_trakt_watchlist":
        if result.get("state"):
            return "I couldn't read your Trakt watchlist. Check its connection and private setup."
        titles = [i["title"] for i in result.get("items", [])]
        return (
            (
                "Your Trakt want-to-watch list includes "
                + ", ".join(titles[:3])
                + ". Streaming availability hasn't been checked."
            )
            if titles
            else "No titles were returned on this Trakt watchlist page."
        )
    if name == "get_context_feed":
        items = result.get("items", [])
        if result.get("state"):
            return "That source is paused or has not been enabled."
        if result.get("view") == "aggregates" and items:
            return (
                "I found "
                + str(len(items))
                + " retained signal intervals. These are sampled observations, not continuous measurements."
            )
        titles = [
            str(
                i["value"].get("title", i["value"].get("label", i["value"].get("signal", "Record")))
            )
            for i in items
        ]
        if not titles:
            if result.get("queried_source") == "home_devices":
                return "I couldn't find a matching reading in the home sensors Amadeus follows. The sensor may not be selected, assigned to that room, or reporting."
            return "No matching records were returned from the selected feed. This is not a complete history of today."
        details = ", ".join(" ".join(t.split())[:80] for t in titles[:3])
        more = (
            " More records are available."
            if result.get("next_offset") is not None or len(titles) > 3
            else ""
        )
        return (
            "The connected records include "
            + details
            + "."
            + more
            + " This is a selected snapshot, not a complete history."
        )
    if name == "get_chores":
        if result.get("state"):
            return "Chore context is paused or not configured."
        titles = [item["title"] for item in result.get("items", [])]
        return (
            "Your chore records include " + ", ".join(titles[:5]) + "."
            if titles
            else "There are no chores in this selected view."
        )
    if name == "get_home_activity":
        return result["summary"]
    if name == "get_companion_locations":
        names = [p["name"] for p in result.get("locations", [])]
        if "current_location" not in result:
            return (
                "My destinations are " + ", ".join(names) + "."
                if names
                else "I have no configured destinations."
            )
        current = next(
            (
                p["name"]
                for p in result.get("locations", [])
                if result.get("current_location") and p.get("id") == result.get("current_location")
            ),
            None,
        )
        position = (
            ("I'm on " + current + ". ")
            if current
            else (
                "I'm moving to " + result["destination_name"] + ". "
                if result.get("destination_name")
                else "My current screen is not confirmed. "
            )
        )
        cue = result.get("room_cue")
        if isinstance(cue, dict) and cue.get("room"):
            position = (
                "A recent NFC scan was in "
                + str(cue["room"])[:100]
                + "; the scanner's identity is unknown. "
                + position
            )
        return position + (
            "Available screens: " + ", ".join(names) + "."
            if names
            else "No destinations are configured."
        )
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
    if name in ("snooze_notifications", "set_notification_source", "set_sender_notification_rule"):
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
        window = result.get("start_date", result.get("date", "requested dates")) + (
            " to " + result["end_date"] + " (end exclusive)" if result.get("end_date") else ""
        )
        coverage = "Configured calendar feed, " + window + ". "
        if not result.get("start_date"):
            coverage += "Upcoming timed events only; excludes all-day and already-started events. "
        return coverage + (
            ("; ".join(str(e["start"]) + " " + e["title"] for e in events[:3]))[:350]
            if events
            else "No events in this view; other calendars are not included."
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

    def __init__(
        self,
        folder,
        notify,
        completed,
        executor=None,
        settings=None,
        clock=None,
        named_targets=None,
    ):
        from . import server

        self.notify, self.completed = notify, completed
        self.executor = executor
        self.clock = clock
        self.named_targets = copy.deepcopy(named_targets)
        self.lock = threading.RLock()
        self.approvals = {}
        self.busy = False
        self.thread_id = "local-conversation"
        self.cancelled = threading.Event()
        self.closed = False
        self.settings = settings or get_config()["conversation"]
        self.policy = get_config()["approvals"]
        allowed = READ_TOOLS | set(TARGETS)

        async def tools():
            return await server.mcp.list_tools()

        self.specs = {
            t.name: {
                "name": t.name,
                "description": t.description.split("\n")[0][:160],
                "parameters": copy.deepcopy(t.inputSchema),
            }
            for t in asyncio.run(tools())
            if t.name in allowed
        }
        # Conversational callers get one canonical watchlist capability. Keep the
        # raw MCP API available to other clients without asking the model to choose
        # between overlapping listing and recommendation descriptions.
        if "get_watch_recommendations" in self.specs:
            self.specs.pop("get_trakt_watchlist", None)
        self.refresh_locations()
        worker_specs = copy.deepcopy(self.specs)
        for name in ("press_bot", "create_reminder"):
            worker_specs[name]["parameters"]["properties"].pop("request_id", None)
            required = worker_specs[name]["parameters"].get("required", [])
            worker_specs[name]["parameters"]["required"] = [
                k for k in required if k != "request_id"
            ]
        worker_specs["press_bot"]["description"] = (
            "Wave or press the SwitchBot once. Takes no arguments; the application assigns its ID."
        )
        worker_specs["get_device_health"]["description"] = (
            "Check whether the Pi, display, speaker and other configured devices are connected or online."
        )
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
                    "evaluation": self.settings.get("evaluation", {}),
                }
            )
            + "\n"
        )
        self.process.stdin.flush()
        try:
            self.worker_info = self._read(120)
            if not self.worker_info.get("ready"):
                raise RuntimeError("Local worker not ready")
            if self.settings.get("evaluation", {}).get("enabled") and not self.worker_info.get(
                "evaluation_enabled"
            ):
                raise RuntimeError("Worker does not support isolated prompt evaluation")
        except Exception:
            self.close()
            raise
        try:
            for task, text in (
                ("agent_route", "Hello."),
                ("agent_step", '{"question":"What is playing?","evidence":[]}'),
            ):
                self.process.stdin.write(
                    json.dumps(
                        {
                            "task": task,
                            "text": text,
                            "persona": current_character()["persona"],
                            "tool_names": sorted(
                                self.specs
                                if task == "agent_route"
                                else READ_TOOLS & self.specs.keys()
                            ),
                            "warmup": True,
                        }
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

    def compose_preference(self, text, context, *, prompt_overrides=None):
        """Tool-free conversational trial; output remains an untrusted memory proposal."""
        with self.lock:
            if self.busy or self.closed or self.process.poll() is not None:
                raise ValueError("Local model unavailable")
            self.busy = True
            self.cancelled.clear()
        try:
            self.process.stdin.write(
                json.dumps(
                    {
                        "task": "preference",
                        "text": text[:1000],
                        "persona": current_character()["persona"],
                        "preferences": context.get("preferences", {}),
                        "source_context": context.get("source_context", []),
                        "previous_question": context.get("last_reply", ""),
                        "history": context.get("history", []),
                        "capabilities": context.get("capabilities", []),
                        "task_state": context.get("task_state", {}),
                        "tool_names": [],
                        "reference_date": self.reference_date(),
                        **self.prompt_payload(prompt_overrides),
                    }
                )
                + "\n"
            )
            self.process.stdin.flush()
            result = self._read()
            if result.get("error") or result.get("tool_call") or self.cancelled.is_set():
                raise ValueError("Conversation generation unavailable")
            try:
                value = json.loads(result["text"])
            except (ValueError, TypeError, KeyError):
                value = None
            if not isinstance(value, dict) or not isinstance(value.get("reply"), str):
                return {
                    "reply": "Could you say that another way? I haven't saved a preference.",
                    "memory": None,
                }
            return {"reply": value["reply"], "memory": value.get("memory")}
        finally:
            with self.lock:
                self.busy = False

    def compose_welcome(self, character, reference):
        """One tool-free generation on the warm worker, separate from user chat."""
        from .welcome import EXAMPLES, validate_intro

        with self.lock:
            if self.busy or self.closed or self.process.poll() is not None:
                raise ValueError("Local model unavailable for welcome")
            self.busy = True
            self.cancelled.clear()
        try:
            style = character.get("style", "configured")
            history = getattr(self, "welcome_history", {})
            self.process.stdin.write(
                json.dumps(
                    {
                        "task": "welcome",
                        "text": "Welcome the user home with a fresh, natural line in your own personality.",
                        "persona": character.get("welcome_persona") or character["persona"],
                        "reference": reference,
                        "examples": EXAMPLES.get(style, EXAMPLES["pip"]),
                        "recent": history.get(style, [])[-3:],
                        "tool_names": [],
                    }
                )
                + "\n"
            )
            self.process.stdin.flush()
            result = self._read()
            if self.cancelled.is_set():
                raise InterruptedError("Welcome cancelled")
            if result.get("error") or result.get("tool_call"):
                raise ValueError("Welcome generation failed")
            intro = validate_intro(result.get("text"))
            history[style] = (history.get(style, []) + [intro])[-3:]
            self.welcome_history = history
            self.notify("welcome_generation", {"selection_s": result.get("selection_s")})
            return intro
        finally:
            with self.lock:
                self.busy = False

    def compose_morning(self, character, slots):
        """Style the whole briefing around typed slots, without private source contents."""
        with self.lock:
            if self.busy or self.closed or self.process.poll() is not None:
                raise ValueError("Local model unavailable for morning greeting")
            self.busy = True
            self.cancelled.clear()
        try:
            self.process.stdin.write(
                json.dumps(
                    {
                        "task": "morning",
                        "text": json.dumps(slots),
                        "persona": character["persona"],
                        "tool_names": [],
                    }
                )
                + "\n"
            )
            self.process.stdin.flush()
            result = self._read()
            if self.cancelled.is_set():
                raise InterruptedError("Morning greeting cancelled")
            if result.get("error") or result.get("tool_call"):
                raise ValueError("Morning greeting generation failed")
            return result.get("text")
        finally:
            with self.lock:
                self.busy = False

    def compose_alexa(self, text, session, character, deadline):
        """Tool-free, isolated Alexa turn on the existing warm model.

        The caller can time out independently; this method still consumes the
        worker reply before releasing busy, so no late output leaks into chat.
        """
        from .alexa_conversation import audio_eligible
        from .profiles import PROFILES
        import re
        import time

        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 600:
            raise ValueError("Use a short question")
        if not re.fullmatch(r"[a-f0-9]{64}", session):
            raise ValueError("Use an opaque conversation session")
        if not 0 < deadline - time.time() <= 8:
            raise TimeoutError("Conversation deadline expired")
        with self.lock:
            if self.busy or self.closed or self.process.poll() is not None:
                raise ValueError("Local model unavailable for Alexa")
            self.busy = True
            self.cancelled.clear()
        try:
            history = getattr(self, "alexa_history", {})
            key = (session, character["style"])
            self.process.stdin.write(
                json.dumps(
                    {
                        "task": "alexa",
                        "text": text,
                        "persona": PROFILES[character["style"]]["persona"],
                        "history": history.get(key, [])[-4:],
                        "tool_names": [],
                    }
                )
                + "\n"
            )
            self.process.stdin.flush()
            result = self._read()
            if time.time() >= deadline or self.cancelled.is_set():
                raise TimeoutError("Conversation deadline expired")
            if result.get("error") or result.get("tool_call"):
                raise ValueError("Conversation generation failed")
            answer = json.loads(result["text"])
            safe = audio_eligible(text, answer)
            if safe:
                history[key] = (
                    history.get(key, [])
                    + [
                        {"role": "user", "content": text},
                        {"role": "assistant", "content": answer["text"]},
                    ]
                )[-4:]
                while len(history) > 12:
                    del history[next(iter(history))]
            else:
                history.pop(key, None)
            self.alexa_history = history
            return {
                "text": answer["text"],
                "audio_safe": safe,
                "character": character["style"],
                "model_s": result.get("selection_s"),
            }
        finally:
            with self.lock:
                self.busy = False

    def refresh_locations(self):
        if "move_companion" not in self.specs:
            return
        from . import locations

        places = locations.configured()
        self.specs["move_companion"]["parameters"]["properties"]["location_id"]["enum"] = [
            p["id"] for p in places
        ]
        self.specs["move_companion"]["description"] = (
            "Move companion to one configured location: "
            + "; ".join(
                p["id"] + " = " + p["name"] + " (" + ", ".join(p["aliases"]) + ")" for p in places
            )
        )

    @staticmethod
    def prompt_payload(prompts):
        if prompts is None:
            return {}
        from .prompt_treatments import validate_prompts

        return {"prompt_scope": "owner_text_lab", "prompt_overrides": validate_prompts(prompts)}

    def text_turn(
        self, text, *, history=None, read_only=False, prompt_overrides=None, task_state=None
    ):
        """Run the same validated tools silently, without voice callbacks or transcript events."""
        if prompt_overrides is not None:
            self.prompt_payload(prompt_overrides)
            read_only = True
        with self.lock:
            if self.busy or self.closed or self.process.poll() is not None:
                raise ValueError("Local model busy or unavailable; no action was retried")
            self.busy = True
            self.cancelled.clear()
        events = []
        answers = []
        self._turn(
            text,
            notify=lambda kind, data: events.append((kind, data)),
            completed=lambda answer, status: answers.append(answer),
            history=history or [],
            conversation_probe=True,
            read_only=read_only,
            prompt_overrides=prompt_overrides,
            task_state=task_state,
        )
        if not answers:
            raise ValueError("Tool outcome uncertain. Check device state before retrying")
        return {
            "reply": answers[-1],
            "conversation": getattr(self, "last_conversational", False),
            "tools": [data["tool"] for kind, data in events if kind == "local_tool"],
            "calls": copy.deepcopy(getattr(self, "last_call_receipts", [])),
            "reply_composition": next(
                (data for kind, data in reversed(events) if kind == "local_tool_reply"), None
            ),
        }

    def render_tool_reply(self, text, name, actual, reference):
        """No tools in this pass. Failure returns the known outcome without retrying it."""
        from .profiles import personality
        from .tool_reply import facts, acceptable, preserve_scope

        if not personality().get("natural_tool_replies", True) or self.cancelled.is_set():
            return reference, False
        try:
            payload = {"question": text[:1000], "facts": facts(name, actual, reference)}
            if name == "get_home_activity" and re.search(r"\b(when|time)\b", text, re.I):
                payload["facts"]["grounded_reference"] = reference
            self.process.stdin.write(
                json.dumps(
                    {
                        "task": "tool_reply",
                        "text": json.dumps(payload),
                        "persona": current_character()["persona"],
                        "tool_names": [],
                    }
                )
                + "\n"
            )
            self.process.stdin.flush()
            generated = self._read().get("text", "").strip()
            generated = preserve_scope(generated, name, actual)
            if acceptable(generated, name, actual, reference):
                return generated, True
        except Exception:
            pass
        return reference, False

    def reference_date(self):
        clock = getattr(self, "clock", None)
        if not clock:
            return None
        zone = get_config()["notifications"]["agenda_timezone"]
        at = datetime.fromtimestamp(clock(), timezone.utc)
        return at.astimezone(None if zone == "local" else ZoneInfo(zone)).date().isoformat()

    def agent_request(
        self,
        text,
        *,
        history=None,
        evidence=None,
        timeout=45,
        allowed_tools=None,
        protocol_repair=False,
        prompt_overrides=None,
        task_state=None,
    ):
        """Native typed tool selection; no lexical eligibility gate for read tools."""
        task = "agent_step" if evidence is not None else "agent_route"
        names = sorted(self.specs if evidence is None else READ_TOOLS & self.specs.keys())
        if allowed_tools is not None:
            names = sorted(set(names) & set(allowed_tools))
        prompt = text[:2000]
        if evidence is not None:
            prompt = json.dumps({"question": text[:2000], "evidence": evidence})
        self.process.stdin.write(
            json.dumps(
                {
                    "task": task,
                    "reference_date": self.reference_date(),
                    "text": prompt,
                    "persona": current_character()["persona"],
                    "history": (history or [])[-4:],
                    "task_state": task_state or {},
                    "tool_names": names,
                    "protocol_repair": protocol_repair,
                    **self.prompt_payload(prompt_overrides),
                    **(
                        {
                            "location_tool": {
                                "type": "function",
                                "function": self.specs["move_companion"],
                            }
                        }
                        if "move_companion" in names
                        else {}
                    ),
                }
            )
            + "\n"
        )
        self.process.stdin.flush()
        return self._read(timeout)

    def _turn(
        self,
        text,
        notify=None,
        completed=None,
        *,
        history=None,
        conversation_probe=False,
        read_only=False,
        prompt_overrides=None,
        task_state=None,
    ):
        from . import server

        notify = notify or self.notify
        completed = completed or self.completed

        specs = {k: v for k, v in self.specs.items() if not read_only or k in READ_TOOLS}
        from .conversation_state import normalize_state, resolve_read_followup, update_task_state
        from .turn_resolution import calendar_window, notification_intent

        self.last_call_receipts = []

        def agent_request(*args, **kwargs):
            if read_only:
                kwargs["allowed_tools"] = READ_TOOLS
            if prompt_overrides is not None:
                kwargs["prompt_overrides"] = prompt_overrides
            kwargs["task_state"] = active_task
            return self.agent_request(*args, **kwargs)

        voice_history = history is None
        character_key = current_character()["style"]
        now = (getattr(self, "clock", None) or time.time)()
        if voice_history:
            fresh = 0 <= now - getattr(self, "agent_task_times", {}).get(character_key, 0) <= 600
            history = getattr(self, "agent_history", {}).get(character_key, []) if fresh else []
            task_state = getattr(self, "agent_tasks", {}).get(character_key, {}) if fresh else {}
        active_task = normalize_state(task_state)
        status = "completed"
        records = []
        action_started = False
        self.last_conversational = False
        try:
            self.refresh_locations()
            clarification = preflight(text)
            if clarification:
                notify("assistant", {"text": clarification, "phase": "final_answer"})
                if not self.cancelled.is_set():
                    completed(clarification, status)
                return
            if read_only:
                from .turn_resolution import assert_action_request, ResolutionError

                for candidate in shortlist(text, self.specs):
                    if candidate in READ_TOOLS:
                        continue
                    try:
                        assert_action_request(text, candidate)
                    except ResolutionError:
                        continue
                    raise ValueError(
                        "This conversation supports read-only lookups; no device action was run."
                    )
            from .conversation_agent import (
                MAX_CALLS,
                MAX_SECONDS,
                conversational,
                dangling_promise,
                evidence,
            )

            self.last_conversational = False
            deadline = time.monotonic() + MAX_SECONDS
            candidates = shortlist(text, specs)
            resolved = resolve_read_followup(text, active_task)
            if resolved and resolved.get("requires_resolution"):
                window = calendar_window(
                    text,
                    now=now,
                    timezone=get_config()["notifications"]["agenda_timezone"],
                    task=active_task,
                )
                resolved = {"name": resolved["name"], "arguments": window} if window else None
            notification = notification_intent(text)
            if notification and notification["name"] in specs:
                resolved = notification
            if resolved and resolved["name"] in specs:
                result = {
                    "text": "",
                    "selection_s": 0,
                    "tool_call": {"name": resolved["name"], "arguments": resolved["arguments"]},
                }
            elif candidates == ["show_calendar_agenda"] and re.match(
                r"\s*(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?(?:show|display)\b",
                text,
                re.I,
            ):
                zone = get_config()["notifications"]["agenda_timezone"]
                requested = calendar_window(text, now=now, timezone=zone)
                day = "today"
                if requested:
                    choices = {
                        d: calendar_window(d, now=now, timezone=zone) for d in ("today", "tomorrow")
                    }
                    day = next((d for d, window in choices.items() if window == requested), None)
                    if day is None:
                        raise ValueError(
                            "I can display today's or tomorrow's agenda. Which should I show?"
                        )
                result = {
                    "text": "",
                    "selection_s": 0,
                    "tool_call": {"name": "show_calendar_agenda", "arguments": {"day": day}},
                }
            elif household_request(text) and "get_home_activity" in specs:
                period = (
                    "yesterday"
                    if re.search(r"\byesterday\b", text, re.I)
                    else "last_24_hours"
                    if re.search(r"\b(?:last|past) 24 hours\b", text, re.I)
                    else "today"
                )
                if re.search(r"\b(week|month|year)\b", text, re.I):
                    raise ValueError(
                        "I can check today, yesterday or the last 24 hours of connected household history."
                    )
                result = {
                    "text": "",
                    "selection_s": 0,
                    "tool_call": {"name": "get_home_activity", "arguments": {"period": period}},
                }
            elif candidates == ["get_companion_locations"]:
                result = {
                    "text": "",
                    "selection_s": 0,
                    "tool_call": {"name": "get_companion_locations", "arguments": {}},
                }
            else:
                result = agent_request(text, history=history)
                # One bounded protocol repair, without trusting or replaying the
                # malformed answer as evidence or changing the user's authority.
                if not result.get("error"):
                    routed = False
                    raw = result.get("text", "").strip()
                    try:
                        parsed = parse_tool_call(raw)
                        value = json.loads(raw) if raw.startswith("{") else None
                        routed = (
                            result.get("tool_call") is not None
                            or parsed is not None
                            or conversational(raw)
                            or isinstance(value, dict)
                            and set(value) == {"clarify"}
                            and isinstance(value["clarify"], str)
                            and bool(value["clarify"].strip())
                        )
                    except ValueError:
                        pass
                    if not routed and not self.cancelled.is_set() and time.monotonic() < deadline:
                        result = agent_request(
                            text,
                            history=history,
                            protocol_repair=True,
                            timeout=max(1, min(45, deadline - time.monotonic())),
                        )
            records, context, seen_calls = [], [], set()
            validation_repairs = 0
            for step in range(MAX_CALLS + 1):
                if time.monotonic() >= deadline:
                    output = (
                        " ".join(r[3] for r in records)[:500]
                        or "I couldn't finish checking that source. No lookup is pending."
                    )
                    break
                if result.get("error"):
                    raise RuntimeError("Local generation failed; no action executed")
                if self.cancelled.is_set():
                    return
                notify(
                    "local_model",
                    {
                        k: result[k]
                        for k in (
                            "selection_s",
                            "prompt_tokens",
                            "generated_tokens",
                            "cached_tokens",
                            "prefill_s",
                        )
                        if k in result
                    },
                )
                output = result["text"].strip()
                call = result["tool_call"] if "tool_call" in result else parse_tool_call(output)
                if call is not None:
                    if read_only and call.get("name") not in specs:
                        raise ValueError(
                            "This conversation supports read-only lookups; no device action was run."
                        )
                    if records and call.get("name") not in READ_TOOLS:
                        raise ValueError(
                            "I won't perform an additional action from a tool result. Please ask separately."
                        )
                    signature = json.dumps(call, sort_keys=True)
                    if signature in seen_calls:
                        output = (
                            " ".join(r[3] for r in records)[:500]
                            or "I couldn't validate that lookup. No tool ran and nothing is pending."
                        )
                        break
                    seen_calls.add(signature)
                    if call.get("name") == "get_calendar_agenda":
                        window = calendar_window(
                            text,
                            now=self.clock() if getattr(self, "clock", None) else None,
                            timezone=get_config()["notifications"]["agenda_timezone"],
                            task=active_task,
                        )
                        if window:
                            call = {"name": "get_calendar_agenda", "arguments": window}
                        elif re.search(r"\b(week|month|year)\b", text, re.I) and not call.get(
                            "arguments", {}
                        ).get("start_date"):
                            raise ValueError(
                                "Which date range should I check? Please give start and end dates."
                            )
                    resolved_device_id = ""
                    if call.get("name") == "speak_on_echo":
                        from .turn_resolution import resolve_named_speaker

                        registry = getattr(self, "named_targets", None)
                        if registry is None:
                            if getattr(self, "executor", None):
                                raise ValueError(
                                    "Synthetic speech requires a fixture speaker registry"
                                )
                            from .echo import speakers

                            names = list(speakers())
                        else:
                            names = registry.get("echo_speakers", [])
                        call = {
                            "name": "speak_on_echo",
                            "arguments": {
                                **call.get("arguments", {}),
                                "speaker": resolve_named_speaker(
                                    text, call.get("arguments", {}).get("speaker"), names
                                ),
                            },
                        }
                    if call.get("name") == "control_spotify" and re.search(
                        r"\b(?:on|to) (?:my |the )?phone\b", text, re.I
                    ):
                        devices = (
                            self.executor("list_spotify_devices", {})
                            if getattr(self, "executor", None)
                            else server.list_spotify_devices()
                        )["devices"]
                        phones = [
                            d
                            for d in devices
                            if d.get("type") == "Smartphone"
                            and d.get("id")
                            and not d.get("is_restricted")
                        ]
                        if len(phones) != 1:
                            raise ValueError(
                                "I can't identify one available phone in Spotify Connect. Open Spotify on your phone, then ask me to check available devices."
                            )
                        resolved_device_id = phones[0]["id"]
                        call = {
                            "name": "control_spotify",
                            "arguments": {
                                **call.get("arguments", {}),
                                "device_id": resolved_device_id,
                            },
                        }
                    try:
                        name, args = validate_call(
                            text,
                            call,
                            specs,
                            self.policy,
                            "local-" + uuid.uuid4().hex,
                            resolved_device_id,
                        )
                    except ValueError:
                        tool = call.get("name")
                        if tool not in READ_TOOLS or tool not in specs or validation_repairs:
                            raise
                        validation_repairs += 1
                        context.append(
                            {
                                "tool": tool,
                                "error": "No tool executed: invalid arguments. Use the exact schema; do not invent date/filter fields.",
                                "parameters": specs[tool]["parameters"],
                            }
                        )
                        result = agent_request(
                            text,
                            history=history,
                            evidence=context,
                            timeout=max(1, min(45, deadline - time.monotonic())),
                        )
                        continue
                    if self.cancelled.is_set():
                        return
                    notify("local_tool", {"tool": name, "selection_s": result["selection_s"]})
                    tool_started = time.monotonic()
                    action_started = name not in READ_TOOLS
                    receipt = {
                        "name": name,
                        "arguments": copy.deepcopy(args),
                        "success": False,
                        "primary": not self.last_call_receipts,
                    }
                    self.last_call_receipts.append(receipt)
                    try:
                        actual = (
                            self.executor(name, args)
                            if getattr(self, "executor", None)
                            else getattr(server, name)(**args)
                        )
                    except Exception:
                        if name not in READ_TOOLS:
                            raise
                        actual = {
                            "error": "unavailable",
                            "summary": "I couldn't read that source; its state is unknown.",
                        }
                    receipt["success"] = (
                        not (
                            isinstance(actual, dict)
                            and (
                                actual.get("error")
                                or actual.get("available") is False
                                or actual.get("accepted") is False
                            )
                        )
                        and not self.cancelled.is_set()
                    )
                    notify(
                        "local_execution",
                        {"tool": name, "duration_s": round(time.monotonic() - tool_started, 3)},
                    )
                    if name == "get_context_feed" and isinstance(actual, dict):
                        actual = {**actual, "queried_source": args.get("source")}
                    reference = (
                        "I couldn't read that source; its state is unknown."
                        if isinstance(actual, dict) and actual.get("error")
                        else acknowledgement(name, actual)
                    )
                    records.append((name, args, actual, reference))
                    if name not in READ_TOOLS:
                        output, natural = self.render_tool_reply(text, name, actual, reference)
                        notify("local_tool_reply", {"model_used": natural, "fallback": not natural})
                        break
                    context.append(evidence(name, args, actual, reference))
                    if len(records) >= MAX_CALLS or time.monotonic() >= deadline:
                        output = " ".join(r[3] for r in records)[:500]
                        break
                    result = agent_request(
                        text,
                        history=history,
                        evidence=context,
                        timeout=max(1, min(45, deadline - time.monotonic())),
                    )
                    continue
                else:
                    if not records:
                        if conversational(output):
                            self.last_conversational = True
                            if conversation_probe:
                                output = ""
                            else:
                                self.process.stdin.write(
                                    json.dumps(
                                        {
                                            "text": text[:2000],
                                            "persona": current_character()["persona"],
                                            "tool_names": [],
                                            "history": history,
                                            "task_state": active_task,
                                        }
                                    )
                                    + "\n"
                                )
                                self.process.stdin.flush()
                                output = self._read().get("text", "").strip()
                        elif output.startswith("{"):
                            try:
                                value = json.loads(output)
                                output = value.get("clarify") if isinstance(value, dict) else None
                            except ValueError:
                                output = None
                            output = (
                                output
                                if isinstance(output, str)
                                else "I couldn't validate that request. Nothing was changed."
                            )
                        else:
                            # The routing pass may only choose a tool, conversation or clarification.
                            output = "I haven't checked a source for that. Please try asking again."
                    else:
                        from .tool_reply import preserve_scope, acceptable

                        for tool, _, value, reference in records:
                            output = preserve_scope(output, tool, value)
                        if dangling_promise(output) or not all(
                            acceptable(output, tool, value, ref) for tool, _, value, ref in records
                        ):
                            output = " ".join(r[3] for r in records)[:500]
                        notify(
                            "local_tool_reply",
                            {
                                "model_used": True,
                                "fallback": output == " ".join(r[3] for r in records)[:500],
                            },
                        )
                    break
            if dangling_promise(output):
                output = "I couldn't finish checking that source. No lookup is pending."
            if voice_history and not self.cancelled.is_set():
                self.agent_tasks = {
                    character_key: update_task_state(
                        active_task, user_text=text, calls=self.last_call_receipts, reply=output
                    )
                }
                self.agent_task_times = {character_key: now}
                self.agent_history = {
                    character_key: (
                        history
                        + [
                            {"role": "user", "content": text[:600]},
                            {"role": "assistant", "content": output[:550]},
                        ]
                    )[-4:]
                }
            notify("assistant", {"text": output[:550], "phase": "final_answer"})
            if not self.cancelled.is_set():
                completed(output[:550], status)
        except ValueError as exc:
            if voice_history:
                self.agent_tasks = {character_key: {}}
            if not self.cancelled.is_set():
                notify("assistant", {"text": str(exc), "phase": "final_answer"})
                completed(str(exc)[:400], status)
        except Exception:
            if voice_history:
                self.agent_tasks = {character_key: {}}
            status = "failed"
            if not action_started and not self.cancelled.is_set():
                output = (
                    " ".join(r[3] for r in records)[:500]
                    or "I couldn't finish checking that source. No lookup is pending."
                )
                notify("assistant", {"text": output, "phase": "final_answer"})
                completed(output, "completed")
            notify(
                "error",
                {
                    "message": "Local turn failed or outcome uncertain. Check the device before retrying."
                },
            )
        finally:
            if voice_history and self.cancelled.is_set():
                self.agent_tasks = {character_key: {}}
                self.agent_task_times = {}
                self.agent_history = {character_key: []}
            with self.lock:
                self.busy = False
            notify(
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
        if self.process.stdin:
            self.process.stdin.close()
        if self.process.stdout:
            self.process.stdout.close()
        self.log.close()

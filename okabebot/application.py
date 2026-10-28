"""Application operations shared by dashboard HTTP routes and MCP callers."""

import time
from . import agenda, scene
from .config import get_config, state_dir
from .reminders import Reminders


class Application:
    ROUTES = {
        "/speaker/volume",
        "/audio/resolve",
        "/audio/stream",
        "/surfaces/move",
        "/surfaces/layout",
        "/surfaces/tv",
        "/surfaces/preview",
        "/surfaces/return",
        "/notifications/preferences",
        "/notifications/senders",
        "/notifications/snooze",
        "/notifications/dismiss",
        "/focus/start",
        "/focus/cancel",
        "/agenda/show",
        "/reminders/create",
        "/reminders/list",
        "/reminders/cancel",
        "/spotify/devices",
        "/echo/speakers",
        "/echo/speak",
    }

    def __init__(self, controller):
        self.controller = controller

    def execute(self, path, data):
        b = self.controller
        if path == "/audio/stream":
            return b.surface_audio.command(data["device_id"], data["command"])
        if path == "/audio/resolve":
            from . import audio_output

            purpose = data.get("purpose", "reply")
            fallback = audio_output.target(purpose)
            if purpose == "announcement":
                return {"target": fallback}
            # Resolve once after movement settles. Never choose an incidental Pi
            # fallback while the character is between screens.
            deadline = time.monotonic() + 8
            while True:
                state = b.surfaces.snapshot()
                if state["current_location"] is not None:
                    break
                if time.monotonic() >= deadline:
                    raise ValueError("Companion is still moving; speech was not redirected")
                time.sleep(0.1)
            place = next(
                (p for p in state["locations"] if p["id"] == state["current_location"]), None
            )
            target = (place or {}).get("audio_target", "default")
            if target == "device":
                return {
                    "target": "browser",
                    "device_id": place["id"],
                    "ready": b.surface_audio.ready(place["id"]),
                }
            return {"target": fallback if target == "default" else target}
        if path.startswith("/surfaces/"):
            base = "http://%s:%s" % (get_config()["web"]["host"], b.port)
            if path == "/surfaces/layout":
                return b.surfaces.layout(data)
            if path == "/surfaces/move":
                return b.surfaces.move(data.get("location_id"), base)
            if path == "/surfaces/return":
                return b.surfaces.return_home()
            if path == "/surfaces/preview":
                return b.surfaces.preview(base)
            from .locations import for_adapter

            return b.surfaces.move(for_adapter("cast")["id"], base)
        if path == "/speaker/volume":
            value = data.get("percent")
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("Volume must be an integer from 0 to 100")
            b.speaker_volume = b.pi({"op": "volume", "percent": value})
            return b.speaker_volume
        if path == "/notifications/senders":
            if data.get("action") == "delete":
                return b.notification_policy.delete_sender(data["source"], data["sender_id"])
            if data.get("action", "set") != "set":
                raise ValueError("Unknown sender rule action")
            return b.notification_policy.set_sender(
                **{k: v for k, v in data.items() if k != "action"}
            )
        if path == "/notifications/preferences":
            return b.notification_policy.update(data)
        if path == "/notifications/snooze":
            minutes = data.get("minutes")
            if type(minutes) is not int or not 0 <= minutes <= 1440:
                raise ValueError("Snooze must be 0–1440 minutes")
            return b.notification_policy.update(
                {"snoozed_until": time.time() + minutes * 60 if minutes else 0}
            )
        if path == "/notifications/dismiss":
            identifier = data.get("id")
            if not isinstance(identifier, str) or not identifier:
                raise ValueError("A notification id is required")
            b.inbox.dismiss(identifier)
            if b.active_notification and identifier in b.active_notification.get(
                "member_ids", [b.active_notification["id"]]
            ):
                b.active_notification = None
                scene.dismiss()
            return {"ok": True}
        if path == "/focus/start":
            return b.focus.start(data.get("minutes"))
        if path == "/focus/cancel":
            b.focus.cancel()
            return b.focus.status()
        if path == "/agenda/show":
            if data:
                if bool(data.get("start_date")) != bool(data.get("end_date")):
                    raise ValueError("Supply both start_date and exclusive end_date")
                settings = get_config()["notifications"]
                if data.get("start_date") and data.get("end_date"):
                    result = agenda.query_calendar(settings, data["start_date"], data["end_date"])
                else:
                    result = agenda.read_calendar(
                        state_dir(), settings["agenda_timezone"], data.get("day", "today")
                    )
                if not result.get("available"):
                    raise ValueError("Calendar unavailable; no agenda card queued")
                body = (
                    "; ".join(e["start"] + " " + e["title"] for e in result["events"][:6])
                    or "No events in this range."
                )
                return b.inbox.publish(
                    "calendar", "Calendar agenda", body[:500], "normal", audio="silent"
                )
            return agenda.publish(
                b.inbox,
                agenda.snapshot(b.sources.state, get_config()["notifications"]["agenda_timezone"]),
            )
        if path.startswith("/reminders/"):
            reminders = Reminders(b.inbox)
            if path.endswith("/create"):
                return reminders.create(**data)
            if path.endswith("/cancel"):
                return reminders.cancel(data.get("id"))
            return {"reminders": reminders.list()}
        if path == "/spotify/devices":
            from .spotify import Spotify

            return Spotify(state_dir(), get_config()["spotify"]).devices()
        if path == "/echo/speakers":
            from .echo import speakers

            return {"speakers": list(speakers())}
        if path == "/echo/speak":
            from .echo import speak

            return speak(**data)
        raise ValueError("Unknown application operation")

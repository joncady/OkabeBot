"""Application operations shared by dashboard HTTP routes and MCP callers."""

import time
from . import agenda, scene
from .config import get_config, state_dir
from .reminders import Reminders


class Application:
    ROUTES = {
        "/speaker/volume",
        "/notifications/preferences",
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
        if path == "/speaker/volume":
            value = data.get("percent")
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("Volume must be an integer from 0 to 100")
            b.speaker_volume = b.pi({"op": "volume", "percent": value})
            return b.speaker_volume
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

"""Application operations shared by dashboard HTTP routes and MCP callers."""

import time
from . import agenda, scene
from .config import get_config, state_dir
from .reminders import Reminders


class Application:
    ROUTES = {
        "/amadeus/text/location",
        "/amadeus/text/policy",
        "/amadeus/text",
        "/amadeus/text/reset",
        "/amadeus/text/feedback",
        "/speaker/volume",
        "/amadeus/shadow",
        "/amadeus/interruptions",
        "/camera/greeting",
        "/character/tone",
        "/mac/screen",
        "/presence/follow",
        "/presence/move",
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
        from .amadeus_text import TextConversation

        self.text_conversation = TextConversation(state_dir() / "amadeus")

    def execute(self, path, data):
        b = self.controller
        if path.startswith("/amadeus/text"):
            chat = self.text_conversation
            if path == "/amadeus/text/location":
                from .chat_location import resolve

                if set(data) - {"location_id", "surface_secret"}:
                    raise ValueError("Choose dashboard location")
                place = resolve(b.surfaces, data)
                return {
                    "location": place,
                    "locations": [
                        {"id": p["id"], "name": p["name"]}
                        for p in b.surfaces.snapshot()["locations"]
                        if p.get("approved")
                    ],
                }
            if path == "/amadeus/text/policy":
                from .preference_confidence import DEFAULTS, KEY as POLICY_KEY
                from .amadeus_habits import preference
                from .amadeus_onboarding import SYSTEM, KEY

                if set(data) - {"auto_accept", "threshold"}:
                    raise ValueError("Unsupported memory policy")
                if "auto_accept" in data and type(data["auto_accept"]) is not bool:
                    raise ValueError("Choose auto accept on or off")
                if "threshold" in data and (
                    type(data["threshold"]) not in (float, int) or not 0.9 <= data["threshold"] <= 1
                ):
                    raise ValueError("Confidence threshold must be 0.90–1.00")
                with chat.lock, chat.store() as s:
                    setup = preference(s, SYSTEM, KEY, {})
                    if not setup.get("profile"):
                        raise ValueError("Save Amadeus setup first")
                    policy = {**DEFAULTS, **preference(s, setup["profile"], POLICY_KEY, {}), **data}
                    if data:
                        s.remember(setup["profile"], POLICY_KEY, policy)
                    return policy
            if path == "/amadeus/text/feedback":
                return chat.feedback(data)
            if path == "/amadeus/text/reset":
                chat.end()
                return {"reset": True}
            if "text" not in data or set(data) - {"text", "location_id", "surface_secret"}:
                raise ValueError("Provide a text message")
            generate = getattr(b.codex, "compose_preference", None)
            if generate is None:
                raise ValueError("Text Amadeus requires the local conversation worker")
            from .chat_location import resolve, ground

            place = resolve(b.surfaces, data)
            text = data["text"]
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000:
                raise ValueError("Use a message of 1–1000 characters")
            result = chat.send(
                ground(text, place), generate, tool_turn=b.codex.text_turn, specs=b.codex.specs
            )
            result["location"] = {"id": place["id"], "name": place["name"]} if place else None
            return result
        if path == "/amadeus/shadow":
            return b.amadeus_shadow.configure(data)
        if path == "/amadeus/interruptions":
            return b.proactive.interruptions(data)
        if path == "/camera/greeting":
            from .camera_greeting import configure

            return configure(data)
        if path == "/character/tone":
            from .profiles import set_personality

            return set_personality(data)
        if path == "/mac/screen":
            return b.mac_screen.configure(data, b.surfaces.snapshot()["locations"])
        if path == "/presence/follow":
            from .presence_control import configure

            return configure(state_dir(), data)
        if path == "/presence/move":
            from .presence_control import status

            p = status(state_dir())
            if (
                set(data) != {"location_id"}
                or not p.get("fresh")
                or not p.get("follow_enabled")
                or data.get("location_id") not in p.get("follow_destinations", [])
                or p.get("healthy_scanners") != 2
                or time.time() < p.get("manual_hold_until", 0)
            ):
                raise ValueError("Presence following is paused or unavailable")
            snapshot = b.snapshot()
            if (
                snapshot["busy"]
                or snapshot["recording"]
                or snapshot["focus"].get("active")
                or snapshot["music"].get("is_playing")
                or snapshot["tv"].get("is_playing")
            ):
                raise ValueError("Companion or media is busy")
            if (
                snapshot["surfaces"].get("phase") not in ("pi", "tv")
                or snapshot["surfaces"].get("current_location") not in p["follow_destinations"]
            ):
                raise ValueError("Character moved outside the follow pair")
            place = next(
                (
                    x
                    for x in snapshot["surfaces"]["locations"]
                    if x["id"] == data["location_id"] and x.get("approved")
                ),
                None,
            )
            if not place:
                raise ValueError("Destination is not approved")
            if place["adapter"] == "cast":
                from pychromecast.config import APP_BACKDROP

                cast = b.surfaces.cast_for(place["id"])
                if (
                    cast is None
                    or cast.status.app_id != APP_BACKDROP
                    or cast.status.is_active_input is not True
                ):
                    raise ValueError("TV must be on its idle Cast input")
            return b.surfaces.move(
                data["location_id"], "http://%s:%s" % (get_config()["web"]["host"], b.port)
            )
        if path == "/audio/stream":
            return b.surface_audio.command(data["device_id"], data["command"])
        if path == "/audio/resolve":
            from . import audio_output

            purpose = data.get("purpose", "reply")
            if purpose == "proactive":
                from .amadeus_habits import preference
                from .amadeus_onboarding import SYSTEM, KEY
                from .amadeus_live import CONFIG

                with b.proactive.store() as store:
                    setup = preference(store, SYSTEM, KEY, {})
                    cfg = preference(store, setup.get("profile", SYSTEM), CONFIG, {})
                surface = b.surfaces.snapshot()
                if (
                    not b.proactive.permitted(setup, cfg)
                    or surface.get("current_location") != cfg.get("destination")
                    or not any(
                        p["id"] == cfg.get("destination") and p["adapter"] == "pi" and p["approved"]
                        for p in surface["locations"]
                    )
                ):
                    raise ValueError("Proactive destination changed; no fallback speaker")
                return {"target": "pi"}
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
            if (place or {}).get("adapter") == "cast" and target == "default":
                target = "device"
            if target == "device":
                return {
                    "target": "browser",
                    "device_id": place["id"],
                    "ready": b.surface_audio.ready(place["id"]),
                }
            return {"target": fallback if target == "default" else target}
        if path.startswith("/surfaces/"):
            if path in ("/surfaces/move", "/surfaces/return", "/surfaces/tv"):
                from .presence_control import manual_move

                manual_move(state_dir())
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

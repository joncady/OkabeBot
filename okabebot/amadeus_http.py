"""Private Amadeus dashboard routes. Paired surfaces/publish tokens have no access."""

import json
import hmac
from pathlib import Path
from urllib.parse import urlsplit


def handle(handler, bridge, *, post=False):
    path = handler.path
    files = {
        "/amadeus/": "amadeus.html",
        "/amadeus.js": "amadeus.js",
        "/amadeus.css": "amadeus.css",
    }
    if not post and path in files:
        name = files[path]
        kind = (
            "text/html"
            if name.endswith("html")
            else "text/css"
            if name.endswith("css")
            else "application/javascript"
        )
        handler.respond(200, (Path(__file__).parent / "web" / name).read_text(), kind)
        return True
    if path in (
        "/amadeus/source/ha",
        "/amadeus/source/availability",
        "/amadeus/source/morning",
        "/amadeus/source/tv-ready",
        "/amadeus/source/person",
    ):
        from .config import state_dir
        from .amadeus_sources import Collector

        folder = state_dir() / "amadeus"
        try:
            expected = (folder / "ha-source-token").read_text().strip()
        except OSError:
            expected = ""
        supplied = handler.headers.get("X-Amadeus-Source-Token", "")
        try:
            permitted = (
                post
                and handler.headers.get("Host") in bridge.allowed_hosts
                and len(expected) >= 32
                and hmac.compare_digest(supplied, expected)
            )
        except TypeError:
            permitted = False
        if not permitted:
            handler.respond(403, {"error": "Source access forbidden"})
            return True
        try:
            size = int(handler.headers.get("Content-Length", 0))
            if not 0 < size <= 4096:
                raise ValueError("Invalid source size")
            handler.connection.settimeout(5)
            data = json.loads(handler.rfile.read(size))
            if path.endswith("availability"):
                result = Collector(folder).availability(data)
            elif path.endswith("person"):
                from .morning_briefing import Briefing

                result = Briefing(folder).update_person(data)
            elif path.endswith("tv-ready"):
                result = bridge.tv_preparation.complete(data)
            elif path.endswith("morning"):
                from .morning import Morning

                result = Morning(folder).observe(data)
                if result.get("prepared") and hasattr(bridge, "dispatch_morning"):
                    bridge.dispatch_morning()
            else:
                result = Collector(folder).home_assistant(data)
            handler.respond(200, result)
        except PermissionError:
            handler.respond(403, {"error": "Source binding forbidden"})
        except (ValueError, TypeError, KeyError):
            handler.respond(400, {"error": "Invalid or stale source metadata"})
        except Exception:
            handler.respond(503, {"error": "Source binding unavailable"})
        return True
    if not path.startswith("/amadeus/api/"):
        return False
    if not handler.authorized():
        handler.respond(403, {"error": "Owner dashboard access required"})
        return True
    origin = handler.headers.get("Origin")
    if origin and urlsplit(origin).netloc != handler.headers.get("Host"):
        handler.respond(403, {"error": "Same-origin access required"})
        return True
    from .amadeus_onboarding import Onboarding, SYSTEM
    from .config import state_dir

    service = None
    try:
        if post:
            size = int(handler.headers.get("Content-Length", 0))
            if not 0 < size <= 8192:
                raise ValueError("Invalid setup request size")
            handler.connection.settimeout(5)
            data = json.loads(handler.rfile.read(size))
        service = Onboarding(state_dir() / "amadeus")
        if path == "/amadeus/api/habits":
            from .amadeus_habits import HabitPlanner, configure, preference, CONFIG_KEY, DEFAULTS

            if not service.settings():
                raise ValueError("Save private setup first")
            if post:
                if not isinstance(data, dict):
                    raise ValueError("Provide habit settings")
                configure(service.store, **data)
            result = {
                "config": preference(service.store, SYSTEM, CONFIG_KEY, DEFAULTS),
                "preview": HabitPlanner(service.store).snapshot(),
                "delivery_enabled": False,
            }
        elif path == "/amadeus/api/opportunities":
            from .amadeus_opportunities import ContextPlanner, configure_context

            if not service.settings():
                raise ValueError("Save private setup first")
            if post:
                if not isinstance(data, dict) or set(data) != {"preferences", "catalog"}:
                    raise ValueError("Provide explicit preferences and catalogue")
                configure_context(
                    service.store, service.subject(), data["preferences"], data["catalog"]
                )
            result = {
                "preview": ContextPlanner(service.store).snapshot(),
                "delivery_enabled": False,
            }
        elif path == "/amadeus/api/habit-feedback" and post:
            from .amadeus_habits import feedback

            if not isinstance(data, dict) or set(data) not in (
                {"kind", "outcome"},
                {"kind", "outcome", "delay_minutes"},
            ):
                raise ValueError("Provide explicit routine feedback")
            feedback(
                service.store,
                service.subject(),
                data["kind"],
                data["outcome"],
                delay_minutes=data.get("delay_minutes", 1440),
            )
            result = {"state": "recorded"}
        elif path == "/amadeus/api/morning-voice" and post:
            from .morning_briefing import Briefing

            result = Briefing(state_dir() / "amadeus").configure(data)
        elif path == "/amadeus/api/morning-present" and post:
            from .morning import Morning

            if (
                data not in ({}, {"replay": True})
                or (data and data.get("replay") is not True)
                or bridge.snapshot().get("busy")
            ):
                raise ValueError("Wait until idle and use an explicit replay choice")
            Morning(state_dir() / "amadeus").reopen()
            result = {
                "accepted": bridge.dispatch_morning(manual=True, replay=data.get("replay", False))
            }
        elif path == "/amadeus/api/tv-prepare" and post:
            from .morning import Morning

            destination = Morning(state_dir() / "amadeus").settings()["destination"]
            if data != {} or not destination or bridge.snapshot().get("busy"):
                raise ValueError("Choose an idle configured destination")
            bridge.surfaces.ensure_scene(destination)
            if not bridge.tv_preparation.configured(destination):
                raise ValueError("Configure TV preparation first")
            result = {
                "ready": bridge.tv_preparation.prepare(
                    destination,
                    lambda: bridge.destination_input_active(destination),
                    wake_cast=lambda: bridge.wake_destination_cast(destination),
                ),
                "input_verified": bridge.destination_input_active(destination) is True,
            }
        elif path == "/amadeus/api/morning":
            from .morning import Morning
            from .morning_briefing import Briefing

            morning = Morning(state_dir() / "amadeus")
            places = bridge.surfaces.snapshot()["locations"]
            if post:
                from .morning import validate

                validate(data, places)
                if data["enabled"] and data["present_on_wake"]:
                    bridge.surfaces.ensure_scene(data["destination"])
            config = morning.configure(data, places) if post else morning.settings()
            destination_ready = False
            if config["destination"]:
                try:
                    bridge.surfaces.ensure_scene(config["destination"])
                    destination_ready = True
                except ValueError:
                    pass
            result = {
                "config": config,
                "destination_ready": destination_ready,
                "tv_preparation_configured": bool(
                    getattr(bridge, "tv_preparation", None)
                    and bridge.tv_preparation.configured(config["destination"])
                ),
                "summary": Briefing(state_dir() / "amadeus").enrich(
                    morning.view(preview=True), bridge.snapshot()
                ),
                "voice": Briefing(state_dir() / "amadeus").settings(),
                "destinations": [
                    {"id": p["id"], "name": p["name"]} for p in places if p.get("adapter") == "cast"
                ],
            }
        elif not post and path == "/amadeus/api/settings":
            result = service.snapshot()
        elif not post and path in ("/amadeus/api/memory", "/amadeus/api/export"):
            result = service.export() if path.endswith("export") else service.memory()
        elif post and path in {
            "/amadeus/api/settings",
            "/amadeus/api/control",
            "/amadeus/api/preference",
            "/amadeus/api/forget",
            "/amadeus/api/feedback",
        }:
            method = {"settings": "save"}.get(path.rsplit("/", 1)[1], path.rsplit("/", 1)[1])
            result = getattr(service, method)(data)
        else:
            handler.respond(404, {"error": "Unknown Amadeus operation"})
            return True
        handler.respond(200, result)
    except (ValueError, TypeError, KeyError):
        handler.respond(400, {"error": "Invalid Amadeus request; check setup choices"})
    except Exception:
        handler.respond(503, {"error": "Private Amadeus storage unavailable"})
    finally:
        if service is not None:
            service.close()
    return True

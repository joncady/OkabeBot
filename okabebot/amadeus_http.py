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
    if path == "/amadeus/source/ha":
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
            handler.respond(200, Collector(folder).home_assistant(data))
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
    from .amadeus_onboarding import Onboarding
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
        if not post and path == "/amadeus/api/settings":
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

"""Owner-only chore management; HA publish-only tag credentials cannot list chores."""

import json
from urllib.parse import urlsplit


def handle(handler, bridge, post=False):
    path = urlsplit(handler.path).path
    if path not in (
        "/chores",
        "/chores/save",
        "/chores/complete",
        "/chores/remove",
        "/chores/snooze",
    ):
        return False
    origin = handler.headers.get("Origin")
    if (
        handler.headers.get("Host") not in bridge.allowed_hosts
        or not handler.authorized()
        or (origin and urlsplit(origin).netloc != handler.headers.get("Host"))
    ):
        handler.respond(403, {"error": "Owner chore access required"})
        return True
    try:
        data = {}
        if post:
            size = int(handler.headers.get("Content-Length", 0))
            if not 0 < size <= 2048:
                raise ValueError("Invalid chore request size")
            handler.connection.settimeout(5)
            data = json.loads(handler.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Use a chore object")
        elif path != "/chores":
            raise ValueError("Use POST for chore actions")
        if path == "/chores" and not data:
            result = bridge.chores.snapshot()
        elif path == "/chores/save" and post:
            result = bridge.chores.save(data)
        elif path in ("/chores/complete", "/chores/remove") and set(data) == {"id"}:
            result = (
                bridge.chores.complete(data["id"])
                if path.endswith("complete")
                else bridge.chores.remove(data["id"])
            )
        elif path == "/chores/snooze" and set(data) == {"id", "days"}:
            result = bridge.chores.snooze(data["id"], data["days"])
        else:
            raise ValueError("Invalid chore action")
        handler.respond(200, result)
    except (ValueError, TypeError, KeyError) as error:
        handler.respond(400, {"error": str(error)})
    except Exception:
        handler.respond(503, {"error": "Chore state unavailable; check before retrying"})
    return True

"""Owner mapping API and separate publish-only HA tag ingress."""

import hmac
import json
from urllib.parse import urlsplit


def handle(handler, bridge, post=False):
    path = urlsplit(handler.path).path
    if path not in (
        "/tags",
        "/tags/learn",
        "/tags/save",
        "/tags/remove",
        "/tags/test",
        "/tags/source",
    ):
        return False
    source = path == "/tags/source"
    if handler.headers.get("Host") not in bridge.allowed_hosts:
        handler.respond(403, {"error": "Tag access forbidden"})
        return True
    if source:
        allowed = (
            post
            and len(bridge.tag_source_token) >= 32
            and hmac.compare_digest(
                handler.headers.get("X-Tag-Token", "").encode(), bridge.tag_source_token.encode()
            )
        )
    else:
        origin = handler.headers.get("Origin")
        allowed = handler.authorized() and (
            not origin or urlsplit(origin).netloc == handler.headers.get("Host")
        )
    if not allowed:
        handler.respond(403, {"error": "Tag access forbidden"})
        return True
    try:
        data = {}
        if post:
            size = int(handler.headers.get("Content-Length", 0))
            if not 0 < size <= 2048:
                raise ValueError("Invalid request size")
            handler.connection.settimeout(5)
            data = json.loads(handler.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Use a tag configuration object")
        elif path != "/tags":
            raise ValueError("Use POST for tag actions")
        if source:
            result = bridge.tags.scan(data)
        elif path == "/tags":
            result = bridge.tags.snapshot()
            from .config import get_config

            result["home_assistant_url"] = get_config()["web"]["home_assistant_url"]
        elif path == "/tags/learn" and not data:
            result = bridge.tags.learn()
        elif path == "/tags/save":
            result = bridge.tags.save(data)
        elif path in ("/tags/remove", "/tags/test") and set(data) == {"tag_id"}:
            result = (
                bridge.tags.remove(data["tag_id"])
                if path.endswith("remove")
                else bridge.tags.dispatch(data["tag_id"])
            )
        else:
            raise ValueError("Invalid tag action")
        handler.respond(200, result)
    except (ValueError, TypeError, KeyError):
        handler.respond(400, {"error": "Invalid tag configuration or stale scan"})
    except Exception:
        handler.respond(
            503, {"error": "Tag service unavailable; check current state before retrying"}
        )
    return True

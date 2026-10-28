"""Limited paired-screen API, separate from dashboard/tool authority."""

import json
from urllib.parse import urlsplit


def handle(handler, bridge, post=False):
    path = urlsplit(handler.path).path
    if not post and path.startswith("/audio/clips/"):
        try:
            if handler.headers.get("Host") not in bridge.allowed_hosts or not path.endswith(".wav"):
                raise ValueError("Invalid audio request")
            from .audio_output import Clips
            from .config import state_dir

            handler.respond(
                200, Clips(state_dir()).read(path.removeprefix("/audio/clips/")[:-4]), "audio/wav"
            )
        except (ValueError, FileNotFoundError):
            handler.respond(404, {"error": "Clip unavailable"})
        return True
    if not post and path == "/companion/ca.cer":
        from .config import get_config
        from pathlib import Path
        from ssl import PEM_cert_to_DER_cert

        certificate = get_config()["web"]["tls"]["ca_certificate"]
        if certificate:
            handler.respond(
                200,
                PEM_cert_to_DER_cert(Path(certificate).read_text()),
                "application/x-x509-ca-cert",
            )
        else:
            handler.respond(404, {"error": "No local CA configured"})
        return True
    public_files = {
        "/tv/wake/": "tv-wake.html",
        "/tv-wake.css": "tv-wake.css",
        "/companion/": "companion.html",
        "/companion.js": "companion.js",
        "/companion.css": "companion.css",
        "/browser-audio.js": "browser-audio.js",
        "/companion-ui.js": "companion-ui.js",
        "/character-environments.js": "character-environments.js",
        "/surface-theme.css": "surface-theme.css",
    }
    if not post and path in public_files:
        from pathlib import Path

        name = public_files[path]
        kind = (
            "text/html"
            if name.endswith("html")
            else "text/css"
            if name.endswith("css")
            else "application/javascript"
        )
        handler.respond(200, (Path(__file__).parent / "web" / name).read_text(), kind)
        return True
    if not post or path not in (
        "/surfaces/register",
        "/surfaces/voice",
        "/surfaces/audio",
        "/surfaces/summon",
    ):
        return False
    try:
        if handler.headers.get("Host") not in bridge.allowed_hosts:
            raise PermissionError("Invalid host")
        origin = handler.headers.get("Origin")
        if origin and urlsplit(origin).netloc != handler.headers.get("Host"):
            raise PermissionError("Cross-origin request forbidden")
        size = int(handler.headers.get("Content-Length", 0))
        if not 0 < size <= (950000 if path.endswith("voice") else 1024):
            raise ValueError("Invalid request size")
        handler.connection.settimeout(10)
        data = json.loads(handler.rfile.read(size))
        token = handler.headers.get("X-Surface-Token", "")
        if path.endswith("summon"):
            item = bridge.surfaces.registry.heartbeat(token)
            if data != {}:
                raise ValueError("Summon only targets this screen")
            from .config import get_config

            base = "http://%s:%s" % (get_config()["web"]["host"], bridge.port)
            handler.respond(200, bridge.surfaces.move(item["id"], base))
        elif path.endswith("audio"):
            item = bridge.surfaces.registry.device(token)
            handler.respond(200, bridge.surface_audio.poll(item["id"], data))
        elif path.endswith("register"):
            if data.get("kind") == "alexa":
                item = bridge.surfaces.registry.register(
                    token, data.get("name"), "alexa", data.get("supported_scenes")
                )
            else:
                item = bridge.surfaces.registry.register(
                    token, data.get("name"), data.get("kind", "browser")
                )
            handler.respond(
                200, {"id": item["id"], "approved": item["approved"], "name": item["name"]}
            )
        else:
            item = bridge.surfaces.registry.device(token)
            if bridge.surfaces.phase != "tv" or bridge.surfaces.active_id != item["id"]:
                raise PermissionError("Move the companion here before speaking")
            bridge.submit_screen_clip(data)
            handler.respond(202, {"accepted": True})
    except PermissionError:
        handler.respond(403, {"error": "Pair this screen in the dashboard and move here first"})
    except Exception:
        handler.respond(
            400, {"error": "Screen request rejected; check connection and current turn"}
        )
    return True

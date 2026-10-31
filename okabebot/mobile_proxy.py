"""Loopback-only, route-limited origin for private Tailscale Serve HTTPS.

No dashboard, MCP, HA webhook, publishing or home-control routes are forwarded.
TLS and tailnet membership remain Tailscale's responsibility, not this proxy's.
"""

import argparse
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

FILES = {
    "/companion/",
    "/companion.js",
    "/companion.css",
    "/surface-theme.css",
    "/browser-audio.js",
    "/companion-ui.js",
    "/character-environments.js",
    "/lab-room.js",
}
GETS = FILES | {
    "/surfaces/state",
    "/surfaces/assets",
    "/mobile/inbox",
    "/mobile/status",
    "/mobile/suggestion",
}
POSTS = {
    "/surfaces/register",
    "/surfaces/heartbeat",
    "/surfaces/ack",
    "/surfaces/closed",
    "/surfaces/summon",
    "/surfaces/return-receiver",
    "/surfaces/audio",
    "/mobile/chat",
    "/mobile/voice",
    "/mobile/push",
    "/mobile/feedback",
}


def handler(hostname, backend_port):
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.forward(False)

        def do_POST(self):
            self.forward(True)

        def forward(self, post):
            route = urlsplit(self.path)
            origin = self.headers.get("Origin")
            valid_host = self.headers.get("Host", "").lower() in (hostname, hostname + ":443")
            if (
                not valid_host
                or route.scheme
                or route.netloc
                or route.path not in (POSTS if post else GETS)
                or (
                    origin and origin not in ("https://" + hostname, "https://" + hostname + ":443")
                )
                or self.headers.get("Transfer-Encoding")
            ):
                self.send_error(403, "Mobile capability only")
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                if not 0 <= n <= (950000 if route.path == "/mobile/voice" else 8192):
                    raise ValueError("Invalid body size")
                self.connection.settimeout(10)
                body = self.rfile.read(n) if post else None
                headers = {
                    "Host": "127.0.0.1:" + str(backend_port),
                    "Content-Type": "application/json",
                    "X-Surface-Token": self.headers.get("X-Surface-Token", ""),
                }
                conn = HTTPConnection("127.0.0.1", backend_port, timeout=150)
                try:
                    conn.request("POST" if post else "GET", self.path, body=body, headers=headers)
                    response = conn.getresponse()
                    data = response.read(4_000_001)
                    if len(data) > 4_000_000:
                        raise ValueError("Response too large")
                    self.send_response(response.status)
                    self.send_header(
                        "Content-Type", response.getheader("Content-Type", "application/json")
                    )
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(data)
                finally:
                    conn.close()
            except Exception:
                self.send_error(503, "Mobile backend unavailable; no automatic retry")

    return Proxy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--port", type=int, default=8772)
    parser.add_argument("--backend-port", type=int, default=8768)
    args = parser.parse_args()
    import re

    if not re.fullmatch(r"[a-z0-9.-]+\.ts\.net", args.hostname):
        parser.error("Use the exact private Tailscale DNS hostname")
    ThreadingHTTPServer(
        ("127.0.0.1", args.port), handler(args.hostname, args.backend_port)
    ).serve_forever()


if __name__ == "__main__":
    main()

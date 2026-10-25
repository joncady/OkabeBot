"""Read-only Spotify playback via PKCE. Tokens never reach the tablet or Codex."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import shlex
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .adapters.media import MediaSnapshot
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


def env_value(name):
    if os.getenv(name):
        return os.environ[name]
    path = Path(os.environ.get("OKABEBOT_CONFIG", "okabebot.local.json")).resolve().parent / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                try:
                    words = shlex.split(value.strip())
                except ValueError:
                    return ""
                return words[0] if words else ""
    return ""


class Spotify:
    def __init__(self, folder, settings):
        self.folder = Path(folder)
        self.path = self.folder / "spotify-tokens.json"
        self.settings = settings
        self.lock = threading.RLock()
        self.pending = None
        self.server = None
        self.error = ""
        self.music = {"is_playing": False}
        self.next_poll = 0
        self.tokens = {}
        try:
            loaded = json.loads(self.path.read_text())
            self.tokens = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            pass

    @property
    def redirect_uri(self):
        return "http://127.0.0.1:%s/spotify/callback" % self.settings["callback_port"]

    def status(self):
        with self.lock:
            client = env_value("SPOTIFY_CLIENT_ID")
            return dict(
                source="api",
                label="Spotify",
                auth_hosts=["accounts.spotify.com"],
                can_authenticate=True,
                configured=bool(client),
                connected=bool(
                    self.tokens.get("refresh_token") and self.tokens.get("client_id") == client
                ),
                error=self.error,
            )

    def save(self, token, client):
        token = dict(token)
        if not token.get("access_token"):
            raise ValueError("Spotify returned no token")
        token["refresh_token"] = token.get("refresh_token") or self.tokens.get("refresh_token")
        token["client_id"] = client
        token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
        self.folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=self.folder, delete=False) as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(token, f)
            tmp = Path(f.name)
        tmp.replace(self.path)
        self.tokens = token

    def exchange(self, fields):
        request = Request(
            "https://accounts.spotify.com/api/token",
            data=urlencode(fields).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def begin(self):
        with self.lock:
            client = env_value("SPOTIFY_CLIENT_ID")
            if not client:
                raise ValueError("Add SPOTIFY_CLIENT_ID to .env on the controller first")
            if self.server is None:
                self.server = ThreadingHTTPServer(
                    ("127.0.0.1", self.settings["callback_port"]), callback_handler(self)
                )
                threading.Thread(target=self.server.serve_forever, daemon=True).start()
            verifier = secrets.token_urlsafe(48)
            state = secrets.token_urlsafe(32)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            self.pending = dict(
                state=state, verifier=verifier, client=client, expires=time.time() + 600
            )
            self.error = ""
            return "https://accounts.spotify.com/authorize?" + urlencode(
                dict(
                    client_id=client,
                    response_type="code",
                    redirect_uri=self.redirect_uri,
                    scope="user-read-playback-state"
                    + (
                        " user-modify-playback-state"
                        if self.settings.get("playback_control")
                        else ""
                    ),
                    state=state,
                    code_challenge_method="S256",
                    code_challenge=challenge,
                )
            )

    def complete(self, query):
        with self.lock:
            pending = self.pending
            state = query.get("state", [""])
            if (
                not pending
                or len(state) != 1
                or not hmac.compare_digest(state[0], pending["state"])
                or time.time() > pending["expires"]
            ):
                raise ValueError("Authorization expired or invalid. Start Connect Spotify again.")
            self.pending = None  # Authorization codes and state are single-use.
            if query.get("error"):
                self.error = "Spotify connection was declined."
                raise ValueError(self.error)
            code = query.get("code", [])
            if len(code) != 1 or not code[0]:
                raise ValueError("Missing authorization code")
            try:
                token = self.exchange(
                    dict(
                        grant_type="authorization_code",
                        client_id=pending["client"],
                        code=code[0],
                        redirect_uri=self.redirect_uri,
                        code_verifier=pending["verifier"],
                    )
                )
                self.save(token, pending["client"])
                self.error = ""
                self.next_poll = 0
            except Exception:
                self.error = "Spotify authorization failed. Check the app redirect URI and allowed user, then reconnect."
                raise ValueError(self.error) from None

    def control(self, action, uri="", device_id=""):
        """Explicit, opt-in playback control independent of the metadata source."""
        if not self.settings.get("playback_control"):
            raise ValueError("Enable spotify.playback_control and reconnect Spotify first")
        if action not in ("play", "pause", "next", "previous"):
            raise ValueError("Unknown playback action")
        if uri and (
            action != "play"
            or not __import__("re").fullmatch(
                r"spotify:(?:track|album|playlist|artist):[A-Za-z0-9]{22}", uri
            )
        ):
            raise ValueError("Use a Spotify track, album, playlist, or artist URI with play")
        if device_id and not __import__("re").fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id):
            raise ValueError("Invalid Spotify device ID")
        client = env_value("SPOTIFY_CLIENT_ID")
        if not client or self.tokens.get("client_id") != client:
            raise ValueError("Connect Spotify on this controller first")
        if "user-modify-playback-state" not in self.tokens.get("scope", "").split():
            raise ValueError("Reconnect Spotify to grant playback control")
        if self.tokens.get("expires_at", 0) < time.time() + 60:
            self.save(
                self.exchange(
                    dict(
                        grant_type="refresh_token",
                        client_id=client,
                        refresh_token=self.tokens["refresh_token"],
                    )
                ),
                client,
            )
        body = None
        if action == "play" and uri:
            body = json.dumps(
                {"uris": [uri]} if uri.startswith("spotify:track:") else {"context_uri": uri}
            ).encode()
        path = action + (("?" + urlencode({"device_id": device_id})) if device_id else "")
        request = Request(
            "https://api.spotify.com/v1/me/player/" + path,
            data=body,
            method="POST" if action in ("next", "previous") else "PUT",
            headers={
                "Authorization": "Bearer " + self.tokens["access_token"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=10):
                return {"accepted": True, "action": action}
        except HTTPError as exc:
            raise ValueError(
                "Spotify playback request failed (HTTP %s); check Premium, permissions and active device"
                % exc.code
            ) from None

    def poll(self):
        with self.lock:
            if time.time() < self.next_poll:
                return dict(self.music)
            self.next_poll = time.time() + self.settings["poll_seconds"]
            client = env_value("SPOTIFY_CLIENT_ID")
            if (
                not client
                or not self.tokens.get("refresh_token")
                or self.tokens.get("client_id") != client
            ):
                self.music = {"is_playing": False}
                return dict(self.music)
            try:
                if self.tokens.get("expires_at", 0) < time.time() + 60:
                    self.save(
                        self.exchange(
                            dict(
                                grant_type="refresh_token",
                                client_id=client,
                                refresh_token=self.tokens["refresh_token"],
                            )
                        ),
                        client,
                    )
                request = Request(
                    "https://api.spotify.com/v1/me/player",
                    headers={"Authorization": "Bearer " + self.tokens["access_token"]},
                )
                with urlopen(request, timeout=10) as response:
                    data = {} if response.status == 204 else json.load(response)
                self.music = playback(data, self.settings["device_name"])
                self.error = ""
            except HTTPError as exc:
                self.music = {"is_playing": False}
                if exc.code == 429:
                    try:
                        wait = max(15, min(3600, int(exc.headers.get("Retry-After", "60"))))
                    except (ValueError, TypeError):
                        wait = 60
                    self.next_poll = time.time() + wait
                    self.error = "Spotify rate limit; updates will resume automatically."
                elif exc.code == 401:
                    self.tokens["expires_at"] = 0
                    self.next_poll = time.time() + 60
                    self.error = "Spotify authorization needs refresh; reconnect if this persists."
                elif exc.code == 403:
                    self.next_poll = time.time() + 60
                    self.error = "Spotify denied access. Check Premium and the app’s allowed users."
                else:
                    self.error = "Spotify is unavailable; updates will retry."
            except Exception:
                self.music = {"is_playing": False}
                self.error = "Spotify connection failed; updates will retry."
            return dict(self.music)

    def read(self):
        with self.lock:
            return MediaSnapshot(self.poll(), {}, self.status())

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


def playback(data, device_name=""):
    device = data.get("device") or {}
    item = data.get("item") or {}
    playing = bool(data.get("is_playing") and item and not device.get("is_private_session"))
    if device_name and device.get("name") != device_name:
        playing = False
    return dict(
        is_playing=playing,
        title=str(item.get("name", ""))[:200] if playing else "",
        artist=", ".join(str(a.get("name", "")) for a in item.get("artists", []))[:200]
        if playing
        else "",
        device=str(device.get("name", ""))[:100],
        updated_at=time.time(),
    )


def callback_handler(spotify):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log OAuth codes or state.

        def do_GET(self):
            parsed = urlsplit(self.path)
            if (
                parsed.path != "/spotify/callback"
                or self.headers.get("Host") != "127.0.0.1:%s" % spotify.settings["callback_port"]
            ):
                self.send_error(404)
                return
            try:
                spotify.complete(parse_qs(parsed.query))
                code, message = (
                    200,
                    "Spotify connected. You can close this tab and return to OkabeBot.",
                )
            except ValueError as exc:
                code, message = 400, str(exc)
            raw = message.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(raw)

    return Handler

"""Local Spotify metadata subscription over Cast; no Spotify Web API polling."""

import threading
import re
import hashlib
import time
from copy import deepcopy
from functools import wraps
from contextlib import nullcontext
from .adapters.media import MediaSnapshot


def synchronized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with getattr(self, "lock", nullcontext()):
            return method(self, *args, **kwargs)

    return call


class CastMusic:
    def __init__(self, settings):
        import pychromecast

        self.lock = threading.RLock()
        self.settings = settings
        self.music = {"is_playing": False}
        self.tv = {}
        self.app = ""
        self.app_icon = None
        self.receiver_title = ""
        self.error = "Connecting to TV"
        self.connected = False
        self.cast = None
        self.browser = None
        self.closed = threading.Event()
        self.library = pychromecast
        self.worker = threading.Thread(target=self._connect, daemon=True)
        self.worker.start()

    def _connect(self):
        while not self.closed.is_set():
            try:
                casts, self.browser = self.library.get_listed_chromecasts(
                    known_hosts=[self.settings["cast_host"]],
                    friendly_names=[self.settings["device_name"]],
                    discovery_timeout=5,
                )
                if not casts:
                    raise RuntimeError("TV not found")
                self.cast = casts[0]
                self.cast.register_connection_listener(self)
                self.cast.register_status_listener(self)
                self.cast.media_controller.register_status_listener(self)
                self.cast.wait(timeout=10)
                self.closed.wait()
                return
            except Exception:
                self.error = "TV unavailable; retrying local connection"
                self.music = {"is_playing": False}
            finally:
                if self.cast:
                    self.cast.disconnect()
                    self.cast = None
                if self.browser:
                    self.browser.stop_discovery()
                    self.browser = None
            self.closed.wait(10)

    @synchronized
    def new_connection_status(self, status):
        self.connected = status.status == "CONNECTED"
        self.error = "" if self.connected else "TV disconnected; reconnecting"
        if not self.connected:
            self.tv = {}
            self.music = {"is_playing": False}
            self.app = ""
            self.receiver_title = ""
            self.pending_media = None

    @synchronized
    def new_cast_status(self, status):
        changed = self.app != (status.display_name or "")
        if changed:
            self.tv = {}
        self.app = status.display_name or ""
        self.app_icon = getattr(status, "icon_url", None)
        self.receiver_title = (
            (getattr(status, "status_text", "") or "").removeprefix("Casting: ").strip()
        )
        if (
            "fubo" in self.app.casefold()
            and re.search(r"\s(?:vs?\.?|versus)\s", self.receiver_title, re.I)
            and (not self.tv or self.tv.get("title") != self.receiver_title)
        ):
            self.tv = dict(
                app=self.app,
                app_icon=self.app_icon,
                title=self.receiver_title,
                state="BUFFERING",
                content_id=None,
                stream_type="LIVE",
                updated_at=time.time(),
            )
        if (status.display_name or "").lower() != "spotify":
            self.music = {"is_playing": False}
        pending = getattr(self, "pending_media", None)
        if pending and time.monotonic() - pending[0] < 5:
            provider = self.media_provider(pending[1])
            if provider and provider == self.app.casefold():
                self.pending_media = None
                self.new_media_status(pending[1])
        # Remain a passive subscriber. MediaController.update_status() can
        # launch Default Media Receiver when the current app lacks its namespace,
        # stealing the TV from the user's selected app. Await callbacks instead.

    @staticmethod
    def media_provider(status):
        kind = (status.content_type or "").casefold()
        if kind.startswith("application/x-spotify"):
            return "spotify"
        if "youtube" in kind:
            return "youtube"
        return None

    @synchronized
    def new_media_status(self, status):
        provider = self.media_provider(status)
        if provider and provider != self.app.casefold():
            # Media and receiver callbacks can arrive in either order.
            self.pending_media = (time.monotonic(), status)
            return
        self.pending_media = None
        title = status.title or (self.receiver_title if "fubo" in self.app.casefold() else "")
        identifier = getattr(status, "content_id", None)
        if "fubo" in self.app.casefold() and title:
            identifier = (
                "title:" + hashlib.sha256((self.app + ":" + title).encode()).hexdigest()[:24]
            )
        elif isinstance(identifier, str) and identifier.startswith(("http://", "https://")):
            identifier = "media:" + hashlib.sha256(identifier.encode()).hexdigest()[:24]
        self.tv = {
            "app": self.app,
            "app_icon": getattr(self, "app_icon", None),
            "title": title,
            "state": (
                "BUFFERING"
                if "fubo" in self.app.casefold()
                and title
                and status.player_state in ("UNKNOWN", "IDLE")
                and getattr(status, "idle_reason", None)
                not in ("CANCELLED", "FINISHED", "INTERRUPTED")
                else status.player_state
            ),
            "position": getattr(status, "current_time", None),
            "duration": getattr(status, "duration", None),
            "playback_rate": getattr(status, "playback_rate", 1),
            "stream_type": getattr(status, "stream_type", None),
            "content_id": identifier,
            "content_type": status.content_type,
            "updated_at": time.time(),
        }
        if not (status.content_type or "").startswith("application/x-spotify"):
            self.music = {"is_playing": False}
            return
        self.music = {
            "is_playing": status.player_state == "PLAYING" and bool(status.title),
            "title": status.title or "",
            "artist": status.artist or "",
            "device": self.settings["device_name"],
            "updated_at": time.time(),
        }

    @synchronized
    def poll(self):
        # Bridge reads the callback's snapshot; this sends no network request.
        return dict(self.music)

    @synchronized
    def status(self):
        return {
            "configured": True,
            "connected": self.connected,
            "error": self.error,
            "source": "cast",
            "label": "Cast TV",
            "can_authenticate": False,
            "app": self.app,
            "has_title": bool(self.tv.get("title")),
        }

    @synchronized
    def read(self):
        return MediaSnapshot(deepcopy(self.music), deepcopy(self.tv), self.status())

    def begin(self):
        raise ValueError("Local Cast mode does not require Spotify sign-in")

    def close(self):
        self.closed.set()
        self.worker.join(timeout=12)

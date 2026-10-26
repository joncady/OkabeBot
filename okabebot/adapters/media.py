"""Provider-neutral media state. Factories own transport/authentication details."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlsplit


@dataclass(frozen=True)
class MediaSnapshot:
    music: dict = field(default_factory=lambda: {"is_playing": False})
    video: dict = field(default_factory=dict)
    status: dict = field(default_factory=dict)


class MediaSource(Protocol):
    def read(self) -> MediaSnapshot:
        """Refresh/read provider state; called only by the media worker."""
        ...

    def status(self) -> dict:
        """Cached health/capabilities, without a network request."""
        ...

    def begin(self) -> str:
        """Begin authentication when can_authenticate is true."""
        ...

    def close(self) -> None: ...


def cast_source(folder, settings):
    from ..cast_music import CastMusic

    return CastMusic(settings)


def spotify_source(folder, settings):
    from ..spotify import Spotify

    return Spotify(folder, settings)


# Add a factory here; config validation and the bridge share this registry.
MEDIA_FACTORIES: dict[str, Callable[[Path, dict], MediaSource]] = {
    "cast": cast_source,
    "api": spotify_source,
}


def create_media_source(name, folder, settings):
    try:
        factory = MEDIA_FACTORIES[name]
    except KeyError:
        raise ValueError("Unknown media source: " + str(name)) from None
    return factory(folder, settings)


def begin_auth(source):
    status = source.status()
    hosts = status.get("auth_hosts", [])
    if not status.get("can_authenticate") or not isinstance(hosts, (list, tuple)) or not hosts:
        raise ValueError("This media source does not use browser authentication")
    url = source.begin()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in hosts:
        raise ValueError("Unexpected provider authentication URL")
    return {"url": url, "allowed_hosts": list(hosts)}

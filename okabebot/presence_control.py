"""Owner controls and expiring current context; no observation history."""

import json
import tempfile
import time
from pathlib import Path


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(value, f)
        name = Path(f.name)
    name.chmod(0o600)
    name.replace(path)


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def status(folder, now=None):
    now = time.time() if now is None else now
    root = Path(folder) / "home-presence"
    runtime = read(root / "runtime.json", {})
    config = read(root / "config.json", {})
    controls = read(root / "follow.json", {"enabled": False})
    fresh = 0 <= now - runtime.get("updated_at", 0) <= 45
    result = dict(
        runtime,
        configured=(root / "config.json").exists(),
        fresh=fresh,
        follow_enabled=controls.get("enabled") is True,
        follow_destinations=[a["id"] for a in config.get("anchors", [])],
        manual_hold_until=controls.get("manual_hold_until", 0),
    )
    if not fresh:
        result.update(presence="unknown", healthy_scanners=0, follow_reason="service unavailable")
    return result


def configure(folder, data):
    if not isinstance(data, dict) or set(data) != {"enabled"} or type(data["enabled"]) is not bool:
        raise ValueError("Choose whether following is enabled")
    root = Path(folder) / "home-presence"
    if not (root / "config.json").exists():
        raise ValueError("Configure the presence bridge first")
    write(root / "follow.json", {"enabled": data["enabled"], "manual_hold_until": 0})
    return status(folder)


def manual_move(folder):
    if not (Path(folder) / "home-presence/config.json").exists():
        return
    path = Path(folder) / "home-presence/follow.json"
    value = read(path, {"enabled": False})
    value["manual_hold_until"] = time.time() + 600
    write(path, value)

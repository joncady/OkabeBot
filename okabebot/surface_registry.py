"""Persistent, explicitly approved browser devices and spatial layout.

A first visit discovers a pending device, never grants controller authority.
Device secrets are client generated, hashed at rest and never appear in snapshots.
"""

import hashlib
import json
import math
import re
import threading
import time
from pathlib import Path

_LOCK = threading.RLock()


def registry_path():
    from .config import state_dir

    return state_dir() / "surface-devices.json"


class Registry:
    def __init__(self, path=None):
        self.path = Path(path) if path else registry_path()
        self.seen = {}

    def read(self):
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"devices": {}, "layout": {}}

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data))
        temporary.chmod(0o600)
        temporary.replace(self.path)

    @staticmethod
    def identity(secret):
        if not isinstance(secret, str) or not re.fullmatch(r"[a-f0-9]{64}", secret):
            raise PermissionError("Invalid device credential")
        return "screen-" + hashlib.sha256(secret.encode()).hexdigest()[:20]

    def register(self, secret, name, kind):
        identity = self.identity(secret)
        if kind not in ("browser", "mac"):
            raise ValueError("Unknown surface kind")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            raise ValueError("Use a short device name")
        with _LOCK:
            data = self.read()
            if identity not in data["devices"]:
                if len(data["devices"]) >= 32:
                    raise ValueError("Device registry full; remove an unused device")
                existing = {p["name"].casefold() for p in data["devices"].values()}
                label, number = name.strip(), 2
                while label.casefold() in existing:
                    label = name.strip()[:35] + " " + str(number)
                    number += 1
                data["devices"][identity] = {
                    "id": identity,
                    "name": label,
                    "adapter": kind,
                    "aliases": [],
                    "approved": False,
                }
                self.save(data)
            self.seen[identity] = time.monotonic()
            return dict(data["devices"][identity])

    def device(self, secret, approved=True):
        identity = self.identity(secret)
        item = self.read()["devices"].get(identity)
        if item is None or (approved and not item["approved"]):
            raise PermissionError("Approve this screen in the dashboard")
        return dict(item)

    def heartbeat(self, secret):
        item = self.device(secret)
        self.seen[item["id"]] = time.monotonic()
        return item

    def list(self):
        return [
            dict(item, available=time.monotonic() - self.seen.get(key, -1000) < 6)
            for key, item in self.read()["devices"].items()
        ]

    def initialize_scenes(self, configured):
        """Reserve home sets for all characters in one explicit setup transaction."""
        from .scene_sets import CATALOG

        home = next(p["id"] for p in configured if p["adapter"] == "pi")
        with _LOCK:
            data = self.read()
            if data.get("scene_world_enabled"):
                raise ValueError("Scene world is already initialized")
            if data.get("scenes"):
                raise ValueError("Resolve existing scene assignments before initializing")
            data["scenes"] = {
                home: {style: choices[0] for style, choices in CATALOG["characters"].items()}
            }
            data["scene_world_enabled"] = True
            self.save(data)

    def update(self, identity, values, configured):
        with _LOCK:
            data = self.read()
            known = {p["id"]: dict(p) for p in configured}
            known.update({key: dict(p) for key, p in data["devices"].items()})
            for key, place in known.items():
                place["name"] = data.get("names", {}).get(key, place["name"])
            if identity not in known:
                raise ValueError("Unknown location")
            if values.get("remove") is True:
                if identity not in data["devices"]:
                    raise ValueError("Configured devices must be changed in configuration")
                del data["devices"][identity]
                data["layout"].pop(identity, None)
                data.get("names", {}).pop(identity, None)
                data.get("audio", {}).pop(identity, None)
                data.get("scenes", {}).pop(identity, None)
                data.get("presentations", {}).pop(identity, None)
                self.seen.pop(identity, None)
                self.save(data)
                return
            if "approved" in values:
                if identity not in data["devices"] or type(values["approved"]) is not bool:
                    raise ValueError("Invalid approval")
                data["devices"][identity]["approved"] = values["approved"]
            if "audio_target" in values:
                target = values["audio_target"]
                allowed = {"default", "pi", "beam"}
                if known[identity]["adapter"] in ("browser", "mac"):
                    allowed.add("device")
                if target not in allowed:
                    raise ValueError("Invalid audio destination")
                data.setdefault("audio", {})[identity] = target
            if "presentation" in values:
                from .scene_sets import CATALOG

                if values["presentation"] not in CATALOG["presentations"]:
                    raise ValueError("Choose Room or Companion presentation")
                if known[identity]["adapter"] == "pi" and values["presentation"] != "companion":
                    raise ValueError("The current Pi adapter supports Companion presentation only")
                data.setdefault("presentations", {})[identity] = values["presentation"]
            if "scene_selections" in values:
                from .scene_sets import validate_selection

                choices = values["scene_selections"]
                if not isinstance(choices, dict) or not choices:
                    raise ValueError("Provide character scene selections")
                for character, selected in choices.items():
                    validate_selection(character, selected)
                    if selected is not None and any(
                        other != identity and mapping.get(character) == selected
                        for other, mapping in data.get("scenes", {}).items()
                    ):
                        raise ValueError("That set already belongs to another location")
                data.setdefault("scenes", {}).setdefault(identity, {}).update(choices)
                # Legacy scenes remain unchanged until the first explicit setup.
                # Thereafter missing assignments block movement, never reuse a set.
                data["scene_world_enabled"] = True
            position = values.get("position")
            if position is not None:
                if (
                    not isinstance(position, list)
                    or len(position) != 2
                    or any(
                        type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 10
                        for v in position
                    )
                ):
                    raise ValueError("Position must contain two coordinates within -10..10")
                data["layout"][identity] = position
            if "name" in values:
                name = values["name"]
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
                    raise ValueError("Use a short name")
                name = name.strip()

                def normalized(value):
                    return re.sub(r"[^\w]+", " ", value.casefold()).strip()

                if any(
                    p["id"] != identity
                    and normalized(name)
                    in {normalized(n) for n in [p["id"], p["name"], *p.get("aliases", [])]}
                    for p in known.values()
                ):
                    raise ValueError("Location names must be unique")
                data.setdefault("names", {})[identity] = name
                if identity in data["devices"]:
                    data["devices"][identity]["name"] = name
            self.save(data)

    def enrich(self, places, include_pending=False):
        data = self.read()
        values = [dict(p, approved=True) for p in places]
        values += [dict(p) for p in data["devices"].values() if include_pending or p["approved"]]
        for i, item in enumerate(values):
            item["presentation"] = data.get("presentations", {}).get(
                item["id"], "room" if item["adapter"] == "cast" else "companion"
            )
            item["scene_selections"] = dict(data.get("scenes", {}).get(item["id"], {}))
            item["name"] = data.get("names", {}).get(item["id"], item["name"])
            item["audio_target"] = data.get("audio", {}).get(
                item["id"], "device" if item["adapter"] in ("browser", "mac") else "default"
            )
            item["position"] = data["layout"].get(
                item["id"],
                [0 if item["adapter"] == "pi" else -1 if item["adapter"] == "cast" else i, 0],
            )
            if item["adapter"] in ("browser", "mac"):
                item["available"] = time.monotonic() - self.seen.get(item["id"], -1000) < 6
        return values

    def scene_world_enabled(self):
        return self.read().get("scene_world_enabled", False)

    def direction(self, origin, target, places):
        positions = {p["id"]: p["position"] for p in self.enrich(places)}
        a, b = positions[origin], positions[target]
        dx, dy = b[0] - a[0], b[1] - a[1]
        return (
            ("left" if dx < 0 else "right") if abs(dx) >= abs(dy) else ("up" if dy < 0 else "down")
        )

"""Persistent, explicitly approved browser devices and spatial layout.

A first visit discovers a pending device, never grants controller authority.
Device secrets are client generated, hashed at rest and never appear in snapshots.
"""

import hashlib
import json
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

    def register(self, secret, name, kind, supported_scenes=None):
        identity = self.identity(secret)
        if kind not in ("browser", "mac", "alexa"):
            raise ValueError("Unknown surface kind")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            raise ValueError("Use a short device name")
        if kind == "alexa":
            from .scene_sets import validate_selection

            if (
                not isinstance(supported_scenes, dict)
                or not supported_scenes
                or len(supported_scenes) > 4
            ):
                raise ValueError("Alexa destinations must declare supported character sets")
            for style, sets in supported_scenes.items():
                if (
                    not isinstance(sets, list)
                    or not 1 <= len(sets) <= 2
                    or any(not isinstance(selected, str) for selected in sets)
                    or len(set(sets)) != len(sets)
                ):
                    raise ValueError("Use supported scene set lists")
                for selected in sets:
                    if selected is None:
                        raise ValueError("Declare concrete supported scene sets")
                    validate_selection(style, selected)
        elif supported_scenes is not None:
            raise ValueError("Scene capability declarations currently belong to Alexa destinations")
        with _LOCK:
            data = self.read()
            previous = data["devices"].get(identity)
            if previous and (
                previous["adapter"] != kind or previous.get("supported_scenes") != supported_scenes
            ):
                raise ValueError(
                    "Forget and reapprove this screen before changing its adapter or capabilities"
                )
            if identity not in data["devices"]:
                if len(data["devices"]) >= 32:
                    raise ValueError("Device registry full; remove an unused device")
                from .config import get_config
                from .locations import normalized

                places = [*get_config()["surfaces"]["locations"], *data["devices"].values()]
                existing = {
                    normalized(value)
                    for place in places
                    for value in [
                        place["id"],
                        data.get("names", {}).get(place["id"], place["name"]),
                        *place.get("aliases", []),
                    ]
                }
                label, number = name.strip(), 2
                while normalized(label) in existing:
                    label = name.strip()[:35] + " " + str(number)
                    number += 1
                data["devices"][identity] = {
                    "id": identity,
                    "name": label,
                    "adapter": kind,
                    "aliases": [],
                    "approved": False,
                }
                if kind == "alexa":
                    data["devices"][identity]["supported_scenes"] = {
                        key: list(sets) for key, sets in supported_scenes.items()
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
                data.get("audio_volumes", {}).pop(identity, None)
                data.get("scenes", {}).pop(identity, None)
                data.get("presentations", {}).pop(identity, None)
                self.seen.pop(identity, None)
                self.save(data)
                return
            if "approved" in values:
                if identity not in data["devices"] or type(values["approved"]) is not bool:
                    raise ValueError("Invalid approval")
                if values["approved"]:
                    from .locations import normalized

                    label = values.get("name", known[identity]["name"])
                    if not isinstance(label, str) or any(
                        other != identity
                        and normalized(label)
                        in {
                            normalized(value)
                            for value in [place["id"], place["name"], *place.get("aliases", [])]
                        }
                        for other, place in known.items()
                    ):
                        raise ValueError("Rename this screen to an unambiguous location name first")
                data["devices"][identity]["approved"] = values["approved"]
            if "audio_target" in values:
                target = values["audio_target"]
                allowed = {"default", "pi", "beam"}
                if known[identity]["adapter"] in ("browser", "mac", "cast"):
                    allowed.add("device")
                if target not in allowed:
                    raise ValueError("Invalid audio destination")
                data.setdefault("audio", {})[identity] = target
            if "audio_volume" in values:
                volume = values["audio_volume"]
                if type(volume) is not int or not 0 <= volume <= 100:
                    raise ValueError("Audio gain must be 0–100")
                data.setdefault("audio_volumes", {})[identity] = volume
            if "presentation" in values:
                from .scene_sets import CATALOG

                if values["presentation"] not in CATALOG["presentations"]:
                    raise ValueError("Choose Room or Companion presentation")
                if known[identity]["adapter"] == "pi" and values["presentation"] != "companion":
                    raise ValueError("The current Pi adapter supports Companion presentation only")
                if known[identity]["adapter"] == "alexa" and values["presentation"] != "room":
                    raise ValueError("The current Alexa adapter supports Room presentation only")
                data.setdefault("presentations", {})[identity] = values["presentation"]
            if "scene_selections" in values:
                from .scene_sets import validate_selection

                choices = values["scene_selections"]
                if not isinstance(choices, dict) or not choices:
                    raise ValueError("Provide character scene selections")
                for character, selected in choices.items():
                    validate_selection(character, selected)
                    supported = known[identity].get("supported_scenes")
                    if (
                        selected is not None
                        and supported is not None
                        and selected not in supported.get(character, [])
                    ):
                        raise ValueError("That set is not supported by this destination's artwork")
                    if selected is not None and any(
                        other != identity and mapping.get(character) == selected
                        for other, mapping in data.get("scenes", {}).items()
                    ):
                        raise ValueError("That set already belongs to another location")
                data.setdefault("scenes", {}).setdefault(identity, {}).update(choices)
                # Legacy scenes remain unchanged until the first explicit setup.
                # Thereafter missing assignments block movement, never reuse a set.
                data["scene_world_enabled"] = True
            if "position" in values or "relative_to" in values or "placement" in values:
                from .surface_layout import positions, validate, DIRECTIONS

                layout = positions(list(known.values()), data["layout"])
                if "relative_to" in values or "placement" in values:
                    anchor, side = values.get("relative_to"), values.get("placement")
                    if (
                        "position" in values
                        or anchor not in known
                        or anchor == identity
                        or side not in DIRECTIONS
                    ):
                        raise ValueError("Choose another screen and a cardinal placement")
                    delta = DIRECTIONS[side]
                    point = [layout[anchor][i] + delta[i] for i in range(2)]
                else:
                    point = values["position"]
                validate(point)
                if any(key != identity and point == other for key, other in layout.items()):
                    raise ValueError("That screen space is occupied; choose an empty grid cell")
                layout[identity] = point
                data["layout"] = layout
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
        from .surface_layout import positions

        all_places = [*places, *data["devices"].values()]
        layout = positions(all_places, data["layout"])
        for item in values:
            item["presentation"] = data.get("presentations", {}).get(
                item["id"], "room" if item["adapter"] in ("cast", "alexa") else "companion"
            )
            item["scene_selections"] = dict(data.get("scenes", {}).get(item["id"], {}))
            item["name"] = data.get("names", {}).get(item["id"], item["name"])
            item["audio_target"] = data.get("audio", {}).get(
                item["id"], "device" if item["adapter"] in ("browser", "mac", "cast") else "default"
            )
            item["audio_volume"] = data.get("audio_volumes", {}).get(
                item["id"], 20 if item["adapter"] == "cast" else 50
            )
            item["position"] = layout[item["id"]]
            if item["adapter"] in ("browser", "mac", "alexa"):
                item["available"] = time.monotonic() - self.seen.get(item["id"], -1000) < 6
        return values

    def scene_world_enabled(self):
        return self.read().get("scene_world_enabled", False)

    def direction(self, origin, target, places):
        positions = {p["id"]: p["position"] for p in self.enrich(places)}
        a, b = positions[origin], positions[target]
        from .surface_layout import direction

        return direction(a, b)

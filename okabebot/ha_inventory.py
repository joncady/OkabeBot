"""Explicit, read-only HA registry preview. No device actions or observation consent."""

import asyncio
from urllib.parse import urlsplit, urlunsplit


def normalize(values):
    if len(values) not in (4, 5):
        raise ValueError("Use supported HA registry responses")
    areas, devices, entities, states = values[:4]
    floors = {
        f["floor_id"]: {"id": f["floor_id"], "name": str(f.get("name", ""))[:200]}
        for f in (values[4] if len(values) == 5 else [])
    }
    rooms = {
        a["area_id"]: {
            "id": a["area_id"],
            "name": str(a.get("name", ""))[:200],
            "floor_id": a.get("floor_id"),
            "floor_name": floors.get(a.get("floor_id"), {}).get("name", ""),
        }
        for a in areas
    }
    device_map = {d["id"]: d for d in devices}
    state_map = {s["entity_id"]: s for s in states}
    entity_map = {e["entity_id"]: e for e in entities}
    result = []
    tags = []
    for identity, entity in entity_map.items():
        if entity.get("disabled_by"):
            continue
        device = device_map.get(entity.get("device_id"), {})
        area = entity.get("area_id") or device.get("area_id")
        state = state_map.get(identity, {})
        result.append(
            {
                "id": identity,
                "name": str(
                    entity.get("name")
                    or state.get("attributes", {}).get("friendly_name")
                    or entity.get("original_name")
                    or identity
                )[:200],
                "area_id": area,
                "room": rooms.get(area, {}).get("name", ""),
                "floor_id": rooms.get(area, {}).get("floor_id"),
                "floor": rooms.get(area, {}).get("floor_name", ""),
                "needs_review": area not in rooms,
                "device_id": entity.get("device_id"),
                "provider": str(entity.get("platform", ""))[:80],
                "available": bool(state) and state.get("state") not in ("unknown", "unavailable"),
            }
        )
    for entity in result:
        raw = entity_map[entity["id"]]
        key = raw.get("unique_id")
        if raw.get("platform") == "tag" and isinstance(key, str) and 1 <= len(key) <= 128:
            tags.append(
                {
                    "tag_id": key,
                    "entity_id": entity["id"],
                    **{k: entity.get(k) for k in ("area_id", "room", "floor_id", "floor")},
                }
            )
    for tag in tags:
        if tag.get("area_id") not in rooms:
            tag.update(area_id=None, room="", floor_id=None, floor="")
    inventory_devices = []
    for identity, device in device_map.items():
        area = device.get("area_id")
        inventory_devices.append(
            {
                "id": identity,
                "name": str(device.get("name_by_user") or device.get("name") or identity)[:200],
                "area_id": area,
                "room": rooms.get(area, {}).get("name", ""),
                "needs_review": area not in rooms,
                "entity_ids": [e["id"] for e in result if e["device_id"] == identity],
            }
        )
    return {
        "floors": list(floors.values()),
        "floor_registry_available": len(values) == 5,
        "rooms": list(rooms.values()),
        "devices": inventory_devices,
        "entities": result,
        "tags": tags,
        "read_only": True,
    }


async def collect(connection):
    import aiohttp

    parts = urlsplit(connection.get("url", ""))
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
    ):
        raise ValueError("Configure a Home Assistant origin first")
    if not connection.get("token"):
        raise ValueError("Connect Home Assistant first")
    url = urlunsplit(
        ("wss" if parts.scheme == "https" else "ws", parts.netloc, "/api/websocket", "", "")
    )
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.ws_connect(url, max_msg_size=2_000_000) as ws:
            if (await ws.receive_json())["type"] != "auth_required":
                raise ValueError("Unexpected HA greeting")
            await ws.send_json({"type": "auth", "access_token": connection["token"]})
            if (await ws.receive_json())["type"] != "auth_ok":
                raise ValueError("HA authorization failed")
            values = []
            for index, command in enumerate(
                (
                    "config/area_registry/list",
                    "config/device_registry/list",
                    "config/entity_registry/list",
                    "get_states",
                ),
                1,
            ):
                await ws.send_json({"id": index, "type": command})
                response = await ws.receive_json()
                if (
                    response.get("id") != index
                    or not response.get("success")
                    or not isinstance(response.get("result"), list)
                ):
                    raise ValueError("HA registry access unavailable")
                values.append(response["result"])
            # Floor support is additive: older HA releases may not expose it.
            await ws.send_json({"id": 5, "type": "config/floor_registry/list"})
            response = await ws.receive_json()
            if response.get("id") != 5:
                raise ValueError("Unexpected HA floor response")
            if response.get("success") and isinstance(response.get("result"), list):
                values.append(response["result"])
            return normalize(values)


def preview(connection):
    return asyncio.run(asyncio.wait_for(collect(connection), 25))


class HomeMap:
    """Private stable room bindings, separate from display coordinates and consent."""

    KEY = "home_map.bindings"

    def __init__(self, feeds):
        self.feeds = feeds

    def snapshot(self, inventory, locations):
        from .amadeus_habits import preference
        from .amadeus_onboarding import SYSTEM

        with self.feeds.store() as store:
            bindings = preference(store, SYSTEM, self.KEY, {})
        areas = {room["id"] for room in inventory["rooms"]}
        return {
            **inventory,
            "locations": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "area_id": bindings.get(p["id"]),
                    "needs_review": bool(bindings.get(p["id"])) and bindings[p["id"]] not in areas,
                }
                for p in locations
                if p.get("approved", True)
            ],
            "changes_control": False,
        }

    def bind(self, data, inventory, locations):
        from .amadeus import encode
        from .amadeus_onboarding import SYSTEM
        from .amadeus_habits import preference

        if not isinstance(data, dict) or set(data) != {"location_id", "area_id"}:
            raise ValueError("Choose a destination and room")
        if data["location_id"] not in {p["id"] for p in locations if p.get("approved", True)}:
            raise ValueError("Choose an approved destination")
        if data["area_id"] is not None and data["area_id"] not in {
            r["id"] for r in inventory["rooms"]
        }:
            raise ValueError("Refresh rooms before assigning")
        with self.feeds.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            bindings = preference(store, SYSTEM, self.KEY, {})
            bindings[data["location_id"]] = data["area_id"]
            store.db.execute(
                "INSERT OR REPLACE INTO preferences VALUES (?,?,?,?)",
                (SYSTEM, self.KEY, encode(bindings), self.feeds.clock()),
            )
        return self.snapshot(inventory, locations)

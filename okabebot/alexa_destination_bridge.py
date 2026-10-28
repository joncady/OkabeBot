"""Optional controller-side relay worker with only paired-screen HTTP authority.

No dashboard token, tools, speech, notifications or household data is uploaded.
The relay carries only a session nonce, transition, phase and command sequence.
"""

import re
import math
import time


class ControllerDestination:
    def __init__(self, store, api, name, *, clock=time.time):
        self.store, self.api, self.name, self.clock = store, api, name, clock
        self.last_poll = None

    def step(self):
        record = self.store.get("session")
        now = self.clock()
        if (
            not record
            or record.get("closed")
            or not 0 <= now - record.get("updated_at", 0) < 3
            or now >= record.get("expires_at", 0)
        ):
            # Do not manufacture a departure ACK. The existing controller waits
            # beyond the receiver's visibility lease before recovering at home.
            return "inactive"
        for key in ("token", "device"):
            if not isinstance(record.get(key), str) or not re.fullmatch(
                r"[a-f0-9]{64}", record[key]
            ):
                raise ValueError("Invalid destination session")
        if (
            type(record.get("ready")) is not bool
            or record.get("painted") not in ("hidden", "pending", "entered", "departed")
            or type(record.get("clock")) not in (int, float)
            or not math.isfinite(record["clock"])
            or not 0 <= record["clock"] < 60000
            or not isinstance(record.get("transition"), str)
            or (record["transition"] and not re.fullmatch(r"[a-f0-9]{32}", record["transition"]))
        ):
            raise ValueError("Invalid destination presentation state")
        from .scene_sets import validate_selection

        style, selected = record["character"], record["set"]
        validate_selection(style, selected)
        if selected is None:
            raise ValueError("Destination artwork must have a concrete scene set")
        secret = record["device"]
        registration = self.api(
            "/surfaces/register",
            {
                "name": self.name,
                "kind": "alexa",
                "supported_scenes": {style: [selected]},
            },
            secret,
        )
        if not registration["approved"]:
            return "approval_required"
        cursor = (record["token"], record["clock"])
        if self.last_poll and cursor[0] == self.last_poll[0] and cursor[1] <= self.last_poll[1]:
            return "waiting_for_poll"
        state = self.api("/surfaces/state", None, secret)
        matches = (
            state.get("character", {}).get("style") == style
            and state.get("environment", {}).get("assigned")
            and state["environment"].get("set") == selected
            and state["environment"].get("presentation") == "room"
        )
        latest = self.store.get("session") or {}
        if (
            latest.get("token") != record["token"]
            or latest.get("device") != record["device"]
            or latest.get("closed")
            or latest.get("clock") != record["clock"]
            or not 0 <= self.clock() - latest.get("updated_at", 0) < 3
        ):
            return "waiting_for_poll"
        previous = self.store.get("command") or {}
        if (
            matches
            and record["ready"]
            and record.get("summon") is True
            and previous.get("requested_move_token") != record["token"]
        ):
            # Claim before the physical request. An uncertain HTTP result is not
            # automatically replayed; a fresh explicit VisitIntent can retry.
            sequence = (
                previous.get("sequence", 0) + 1 if previous.get("token") == record["token"] else 1
            )
            self.store.put(
                "command",
                {
                    "token": record["token"],
                    "phase": "hidden",
                    "generation": state["transition_id"],
                    "sequence": sequence,
                    "receiver_elapsed_ms": int(record["clock"]),
                    "updated_at": now,
                    "requested_move_token": record["token"],
                },
            )
            self.api("/surfaces/summon", {}, secret)
            state = self.api("/surfaces/state", None, secret)
        phase, transition = state["phase"], state["transition_id"]
        if not isinstance(transition, str) or not re.fullmatch(r"[a-f0-9]{32}", transition):
            raise ValueError("Invalid controller transition")
        active = phase in ("preparing", "leaving_pi", "entering_tv", "tv", "leaving_tv")
        if matches and record["ready"] and active:
            self.api("/surfaces/heartbeat", {}, secret)
            if record["transition"] == transition:
                kind = (
                    "entered"
                    if record["painted"] == "entered" and phase == "entering_tv"
                    else "departed"
                    if record["painted"] == "departed" and phase == "leaving_tv"
                    else None
                )
                if kind:
                    self.api("/surfaces/ack", {"kind": kind, "transition_id": transition}, secret)
                    state = self.api("/surfaces/state", None, secret)
                    phase, transition = state["phase"], state["transition_id"]
        target = (
            {"entering_tv": "entering", "tv": "present", "leaving_tv": "leaving"}.get(
                phase, "hidden"
            )
            if matches and record["ready"]
            else "hidden"
        )
        previous = self.store.get("command") or {}
        sequence = (
            previous.get("sequence", 0) + 1 if previous.get("token") == record["token"] else 1
        )
        self.store.put(
            "command",
            {
                "token": record["token"],
                "phase": target,
                "generation": transition,
                "sequence": sequence,
                "receiver_elapsed_ms": int(record["clock"]),
                "updated_at": now,
                **(
                    {"requested_move_token": previous["requested_move_token"]}
                    if previous.get("requested_move_token") == record["token"]
                    else {}
                ),
            },
        )
        self.last_poll = cursor
        return "connected" if matches else "artwork_mismatch"


class SurfaceClient:
    def __init__(self, base):
        from urllib.parse import urlsplit

        url = urlsplit(base)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise ValueError("Use the controller base URL without an access key")
        self.base = base.rstrip("/")

    def __call__(self, path, data, token):
        import json
        from urllib.request import Request, urlopen

        request = Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json", "X-Surface-Token": token},
        )
        with urlopen(request, timeout=3) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Controller response exceeds limit")
        return json.loads(body)

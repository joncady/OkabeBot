"""Bounded PCM relay to an explicitly enabled, paired browser audio session."""

import base64
import secrets
import threading
import time


class AudioHub:
    def __init__(self):
        self.condition = threading.Condition()
        self.receivers = {}
        self.streams = {}
        self.cursor = 0
        self.epoch = secrets.token_hex(16)

    def ready(self, device):
        r = self.receivers.get(device, {})
        return bool(r.get("enabled") and time.monotonic() - r.get("seen", 0) < 4)

    def poll(self, device, data):
        session, after = data.get("session"), data.get("after", 0)
        if (
            not isinstance(session, str)
            or len(session) != 32
            or type(after) is not int
            or not 0 <= after <= 10**12
            or type(data.get("enabled")) is not bool
        ):
            raise ValueError("Invalid audio receiver")
        with self.condition:
            old = self.receivers.get(device)
            if old and (
                old["session"] != session
                or time.monotonic() - old["seen"] >= 4
                or not data["enabled"]
            ):
                for identifier, stream in self.streams.items():
                    if stream["device"] == device and not stream["aborted"]:
                        stream["aborted"] = True
                        self.emit(stream, identifier, "abort")
            self.receivers[device] = {
                "session": session,
                "enabled": data["enabled"],
                "seen": time.monotonic(),
            }
            finished = data.get("finished")
            if finished in self.streams:
                stream = self.streams[finished]
                if stream["device"] == device and stream["session"] == session and stream["ended"]:
                    stream["played"] = True
            self.condition.notify_all()
            events = []
            for stream in self.streams.values():
                if stream["device"] == device and stream["session"] == session:
                    events.extend(
                        e
                        for e in stream["events"]
                        if e["cursor"] > after and (not stream["aborted"] or e["kind"] == "abort")
                    )
            return {"epoch": self.epoch, "events": sorted(events, key=lambda e: e["cursor"])[:8]}

    def command(self, device, data):
        op = data.get("op")
        with self.condition:
            if op == "stream_start":
                if not self.ready(device):
                    raise ValueError("Enable sound on the destination screen first")
                self.streams = {
                    k: v
                    for k, v in self.streams.items()
                    if time.monotonic() - v["created"] < 90 and not v["played"] and not v["aborted"]
                }
                if len(self.streams) >= 4:
                    raise ValueError("Audio relay busy")
                identifier = secrets.token_hex(16)
                stream = {
                    "device": device,
                    "session": self.receivers[device]["session"],
                    "created": time.monotonic(),
                    "events": [],
                    "bytes": 0,
                    "sequence": 0,
                    "ended": False,
                    "played": False,
                    "aborted": False,
                    "started": time.time() + 0.25,
                }
                self.streams[identifier] = stream
                self.emit(stream, identifier, "start")
                return {"stream_id": identifier}
            identifier = data.get("stream_id")
            stream = self.streams.get(identifier)
            if stream is None or stream["device"] != device:
                raise ValueError("Unknown stream")
            if op == "stream_abort":
                stream["aborted"] = True
                self.emit(stream, identifier, "abort")
                return {"aborted": True}
            if stream["aborted"] or not self.ready(device):
                raise ValueError("Audio receiver disconnected; no fallback replay")
            if op == "stream_chunk":
                raw = base64.b64decode(data.get("pcm_base64", ""), validate=True)
                if (
                    stream["ended"]
                    or data.get("sequence") != stream["sequence"]
                    or not 0 < len(raw) <= 240000
                    or len(raw) % 2
                    or stream["bytes"] + len(raw) > 1440000
                ):
                    raise ValueError("Invalid or excessive PCM")
                stream["bytes"] += len(raw)
                stream["sequence"] += 1
                self.emit(stream, identifier, "chunk", pcm_base64=data["pcm_base64"])
                return {"playback_started_at": stream["started"]}
            if op == "stream_end":
                if not stream["ended"]:
                    stream["ended"] = True
                    self.emit(stream, identifier, "end")
                deadline = time.monotonic() + 35
                while (
                    not stream["played"]
                    and not stream["aborted"]
                    and self.ready(device)
                    and time.monotonic() < deadline
                ):
                    self.condition.wait(0.25)
                if not stream["played"]:
                    stream["aborted"] = True
                    self.emit(stream, identifier, "abort")
                    raise ValueError("Browser playback unconfirmed; no automatic replay")
                return {"played": True}
            raise ValueError("Unsupported audio operation")

    def emit(self, stream, identifier, kind, **values):
        self.cursor += 1
        stream["events"].append(dict(cursor=self.cursor, stream_id=identifier, kind=kind, **values))

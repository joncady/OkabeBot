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

    def expire(self):
        """Keep only bounded transient streams; never replay an expired utterance."""
        now = time.monotonic()
        for identifier, stream in list(self.streams.items()):
            if now - stream["created"] > 90:
                del self.streams[identifier]

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
            self.expire()
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
            for stream in self.streams.values():
                if stream["device"] == device and stream["session"] == session:
                    stream["events"] = [e for e in stream["events"] if e["cursor"] > after]
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

    def command(self, device, data, check=None):
        op = data.get("op")
        with self.condition:
            self.expire()
            if check:
                check()
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
                buffer_options = {}
                if "startup_buffer_ms" in data:
                    startup = data["startup_buffer_ms"]
                    if type(startup) is not int or not 100 <= startup <= 2000:
                        del self.streams[identifier]
                        raise ValueError("Invalid startup buffer")
                    buffer_options["startup_buffer_ms"] = startup
                self.emit(
                    stream,
                    identifier,
                    "start",
                    sample_rate=24000,
                    channels=1,
                    encoding="pcm_s16le",
                    **buffer_options,
                )
                return {"stream_id": identifier}
            identifier = data.get("stream_id")
            stream = self.streams.get(identifier)
            if stream is None or stream["device"] != device:
                raise ValueError("Unknown stream")
            if op == "stream_abort":
                stream["aborted"] = True
                self.emit(stream, identifier, "abort")
                return {"aborted": True}

            def current():
                if (
                    self.streams.get(identifier) is not stream
                    or stream["aborted"]
                    or not self.ready(device)
                    or self.receivers[device]["session"] != stream["session"]
                    or time.monotonic() - stream["created"] > 90
                ):
                    raise ValueError("Audio receiver disconnected; no fallback replay")

            current()
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
                deadline = time.monotonic() + 8
                while (
                    sum(len(e.get("pcm_base64", "")) * 3 // 4 for e in stream["events"]) + len(raw)
                    > 240000
                ):
                    if check:
                        check()
                    current()
                    if time.monotonic() > deadline:
                        raise ValueError("Audio receiver is not consuming its bounded queue")
                    self.condition.wait(0.1)
                current()
                if stream["ended"] or data.get("sequence") != stream["sequence"]:
                    raise ValueError("Stream changed while waiting for capacity")
                stream["bytes"] += len(raw)
                stream["sequence"] += 1
                self.emit(
                    stream,
                    identifier,
                    "chunk",
                    sequence=stream["sequence"] - 1,
                    pcm_base64=data["pcm_base64"],
                )
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
                    if check:
                        check()
                    current()
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
        self.condition.notify_all()

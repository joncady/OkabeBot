"""Bounded skill-session relay protocol over an injected private durable store.

Not enabled by the deployed skill. The store must offer get(key)/put(key, value)
with bounded JSON reads. No household tools, transcripts, raw account identifiers,
URLs from slots, or automatic movement are accepted here.
"""

import hashlib
import math
import secrets
import time

from .alexa_destination import document, update


class DestinationRelay:
    def __init__(self, store, assets, *, clock=time.time, nonce=lambda: secrets.token_hex(32)):
        self.store, self.assets, self.clock, self.nonce = store, assets, clock, nonce

    @staticmethod
    def identity(event):
        system = event["context"]["System"]
        values = [
            system["application"]["applicationId"],
            system["user"]["userId"],
            system["device"]["deviceId"],
        ]
        if any(not isinstance(v, str) or not 1 <= len(v) <= 1000 for v in values):
            raise ValueError("Invalid Alexa screen identity")
        return hashlib.sha256("\0".join(values).encode()).hexdigest()

    @staticmethod
    def session(event):
        identity = event.get("session", {}).get("sessionId")
        return (
            hashlib.sha256(identity.encode()).hexdigest()
            if isinstance(identity, str) and identity
            else None
        )

    def launch(self, event):
        interfaces = event["context"]["System"]["device"].get("supportedInterfaces", {})
        if "Alexa.Presentation.APL" not in interfaces:
            raise ValueError("This destination needs an APL screen")
        now, token = self.clock(), self.nonce()
        assets = self.assets()
        result = document(token, assets["background"], assets["frames"])
        record = {
            "token": token,
            "device": self.identity(event),
            "session": self.session(event),
            "started_at": now,
            "expires_at": now + 60,
            "updated_at": now,
            "clock": 0,
            "ready": False,
            "painted": "hidden",
            "transition": "",
            "closed": False,
            "summon": event["request"]["type"] == "IntentRequest"
            and event["request"].get("intent", {}).get("name") == "VisitIntent",
            "character": assets["character"],
            "set": assets["set"],
        }
        for _ in range(6):
            previous, version = self.store.read("session")
            if previous and previous["started_at"] > now:
                return {"version": "1.0", "response": {}}
            if self.store.compare_put("session", record, version):
                return result
        raise RuntimeError("Destination session changed; retry launch")

    def poll(self, event):
        request = event["request"]
        args = request.get("arguments")
        if not isinstance(args, list) or len(args) != 6 or args[0] != "destination-poll":
            raise ValueError("Invalid destination event")
        _, token, generation, painted, ready, elapsed = args
        if (
            type(ready) is not bool
            or painted not in ("hidden", "pending", "entered", "departed")
            or not isinstance(generation, str)
            or (
                generation
                and (len(generation) != 32 or any(c not in "0123456789abcdef" for c in generation))
            )
            or type(elapsed) not in (int, float)
            or not math.isfinite(elapsed)
            or not 0 <= elapsed < 60000
        ):
            raise ValueError("Invalid receiver state")
        for _ in range(6):
            record, version = self.store.read("session")
            if (
                not record
                or record["device"] != self.identity(event)
                or record["token"] != token
                or request.get("token") != token
            ):
                raise PermissionError("Unrelated screen session")
            now = self.clock()
            if record["closed"] or now >= record["expires_at"] or elapsed < record["clock"]:
                return {"version": "1.0", "response": {}}
            record.update(
                clock=elapsed, ready=ready, painted=painted, transition=generation, updated_at=now
            )
            if self.store.compare_put("session", record, version):
                break
        else:
            return {"version": "1.0", "response": {}}
        command = self.store.get("command")
        if (
            not command
            or command.get("token") != token
            or not 0 <= now - command.get("updated_at", 0) < 4
            or type(command.get("receiver_elapsed_ms")) is not int
            or not 0 <= elapsed - command["receiver_elapsed_ms"] < 4000
        ):
            return {"version": "1.0", "response": {}}
        return update(
            token,
            command["phase"],
            command["generation"],
            sequence=command["sequence"],
            receiver_elapsed_ms=command["receiver_elapsed_ms"],
        )

    def closed(self, event):
        for _ in range(6):
            record, version = self.store.read("session")
            if not (
                record
                and record["device"] == self.identity(event)
                and record.get("session")
                and record["session"] == self.session(event)
            ):
                return
            if record["closed"]:
                return
            record.update(closed=True, ready=False, updated_at=self.clock())
            if self.store.compare_put("session", record, version):
                return
        raise RuntimeError("Destination session changed; retry close")


class PrivateDestinationStore:
    """Two private S3 JSON objects; no list operation or caller-provided keys."""

    KEYS = {"session": "surface/session.json", "command": "surface/command.json"}

    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket

    def get(self, key):
        return self.read(key)[0]

    def read(self, key):
        import json

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.KEYS[key])
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") == "NoSuchKey":
                return None, None
            raise
        stream = response["Body"]
        try:
            body = stream.read(16385)
        finally:
            stream.close()
        if len(body) > 16384:
            raise ValueError("Destination state exceeds limit")
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError("Destination state must be an object")
        version = response.get("ETag")
        if not isinstance(version, str) or not version:
            raise ValueError("Missing destination object version")
        return value, version

    def put(self, key, value):
        return self._put(key, value)

    def compare_put(self, key, value, version):
        try:
            self._put(
                key,
                value,
                **({"IfMatch": version} if version is not None else {"IfNoneMatch": "*"}),
            )
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") in (
                "PreconditionFailed",
                "ConditionalRequestConflict",
            ):
                return False
            raise
        return True

    def _put(self, key, value, **condition):
        import json

        body = json.dumps(value, allow_nan=False).encode()
        if len(body) > 16384 or not isinstance(value, dict):
            raise ValueError("Invalid destination state")
        self.client.put_object(
            Bucket=self.bucket,
            Key=self.KEYS[key],
            Body=body,
            ContentType="application/json",
            CacheControl="no-store",
            ServerSideEncryption="AES256",
            **condition,
        )

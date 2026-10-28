"""Direct external-screen handoff: prepare target, depart source, enter target.

The Pi stays away throughout. A failure may recover there after visibility leases;
normal movement never uses it as an intermediate destination.
"""

import secrets
import threading
import time
import uuid


def opposite(direction):
    return {"left": "right", "right": "left", "up": "down", "down": "up"}[direction]


class DirectTransfer:
    def __init__(self, owner, target, base):
        self.owner = owner
        self.identifier = uuid.uuid4().hex
        self.source_id, self.source_token = owner.active_id, owner.token
        self.source_session, self.source_active = owner.receiver_session, owner.receiver_active
        self.source_seen = owner.last_seen
        self.source_departed = False
        self.target_id, self.target_token = target["id"], secrets.token_urlsafe(32)
        self.target_cast = target["adapter"] == "cast"
        self.target_session, self.target_active = None, False
        self.target_ready = False
        self.target_seen = self.started = time.monotonic()
        self.target_error = ""
        self.stage = "preparing"
        self.direction = owner.registry.direction(
            self.source_id, self.target_id, owner.settings["locations"]
        )
        self.base = base

    def start(self):
        s = self.owner
        s.direct, s.identifier, s.phase, s.error = self, self.identifier, "preparing_direct", ""
        s.started = self.started
        if self.target_cast:
            url = self.base + "/tv/#" + self.target_token
            threading.Thread(target=s._launch, args=(url, self), daemon=True).start()
        return s.snapshot()

    def role(self, token):
        item = self.owner.registered(token)
        if item:
            return (
                "source"
                if item["id"] == self.source_id
                else "target"
                if item["id"] == self.target_id
                else None
            )
        if token and secrets.compare_digest(token, self.source_token):
            return "source"
        if token and secrets.compare_digest(token, self.target_token):
            return "target"
        return None

    def heartbeat(self, token):
        role = self.role(token)
        now = time.monotonic()
        if role == "source":
            self.source_seen = now
            if not self.source_departed:
                self.owner.last_seen = now
        elif role == "target":
            self.target_seen, self.target_ready = now, True
            if self.target_cast:
                cast = self.owner.cast_for(self.target_id)
                if cast:
                    from pychromecast.config import APP_DASHCAST

                    if cast.status.app_id == APP_DASHCAST:
                        self.target_session = cast.status.session_id
                        self.target_active |= getattr(cast.status, "is_active_input", None) is True
        else:
            raise PermissionError("Unrelated receiver")
        item = self.owner.registered(token)
        if item:
            self.owner.registry.heartbeat(token)
        return self.owner.snapshot()

    def decorate(self, token, status):
        role = self.role(token)
        if role == "source":
            status["phase"] = (
                "tv"
                if self.stage == "preparing"
                else "leaving_tv"
                if self.stage == "leaving"
                else "idle"
            )
            status["tv_side"] = opposite(self.direction)
        elif role == "target":
            status["phase"] = "entering_tv" if self.stage == "entering" else "preparing"
            status["tv_side"] = self.direction
        else:
            status["phase"] = "idle"
        return status

    def acknowledge(self, token, kind, identifier):
        if identifier != self.identifier:
            raise PermissionError("Stale transfer acknowledgement")
        role = self.role(token)
        if role == "source" and kind == "departed" and self.stage == "leaving":
            self.source_departed = True
            self.commit()
        elif role == "target" and kind == "entered" and self.stage == "entering":
            s = self.owner
            s.phase, s.started, s.last_seen = "tv", time.monotonic(), self.target_seen
            s.direct = None
        elif role not in ("source", "target"):
            raise PermissionError("Unrelated receiver")
        return self.owner.snapshot()

    def closed(self, token, identifier):
        if identifier != self.identifier:
            raise PermissionError("Stale receiver close")
        role = self.role(token)
        if role == "source":
            self.source_departed = True
        elif role == "target":
            self.target_error = "Destination screen closed"
        else:
            raise PermissionError("Unrelated receiver")
        return self.owner.snapshot()

    def cancel(self, message):
        s = self.owner
        s._quit_receiver(self.target_id, self.target_session)
        if self.stage == "preparing" and not self.source_departed:
            s.direct, s.phase, s.error, s.last_seen = None, "tv", message[:240], self.source_seen
        else:
            s.direct = None
            s._recover(message)

    def commit(self):
        s = self.owner
        # Only after a departed ACK or expired/confirmed-closed source visibility.
        s._quit_receiver(self.source_id, self.source_session)
        self.stage = "entering"
        s.active_id, s.token = self.target_id, self.target_token
        s.receiver_session, s.receiver_active = self.target_session, self.target_active
        s.last_seen, s.ready = self.target_seen, True
        s.phase, s.started, s.travel_direction = "entering_tv", time.monotonic(), self.direction
        self.started = s.started

    def tick(self, now):
        s = self.owner
        if now - s.last_renewal > 3:
            s.rpc(s._command("away"))
            s.last_renewal = now
        if (
            self.target_error
            or (self.target_ready and now - self.target_seen > s.RECEIVER_LEASE)
            or s._location_gone(self.target_id, self.target_session, self.target_active)
        ):
            self.cancel(self.target_error or "Destination disconnected during movement")
            return
        if not self.source_departed and (
            s._location_gone(self.source_id, self.source_session, self.source_active)
            or now - self.source_seen > s.RECEIVER_LEASE + 1
        ):
            self.source_departed = True
        if self.stage == "preparing":
            if self.target_ready:
                if self.source_departed:
                    self.commit()
                else:
                    self.stage, self.started, s.phase, s.started = "leaving", now, "leaving_tv", now
            elif now - self.started > 20:
                self.cancel("Destination did not become ready; companion stayed at its source")
        elif self.stage == "leaving":
            if self.source_departed:
                self.commit()
            elif now - self.started > 15:
                self.cancel("Source departure was not confirmed")
        elif now - self.started > 15:
            self.cancel("Destination arrival was not confirmed")

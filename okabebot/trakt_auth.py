"""Owner-initiated device authorization; private credentials and bounded polling."""

import threading
from urllib.error import HTTPError
from .adapters.context.providers import request
from .amadeus import encode
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY


class TraktAuth:
    def __init__(self, feeds, read=request):
        self.feeds, self.read = feeds, read
        self.pending = None
        self.lock = threading.Lock()

    def call(self, path, data):
        return self.read(
            "https://api.trakt.tv/oauth/" + path,
            {
                "Content-Type": "application/json",
                "User-Agent": "OkabeBot/0.1.0",
                "trakt-api-key": data["client_id"],
                "trakt-api-version": "2",
            },
            data,
        )

    def save(self, old, new):
        with self.feeds.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            if preference(store, SYSTEM, "feed_connection.trakt", {}) != old:
                raise ValueError("Connection changed; authorize again")
            store.db.execute(
                "INSERT OR REPLACE INTO preferences VALUES (?,?,?,?)",
                (SYSTEM, "feed_connection.trakt", encode(new), self.feeds.clock()),
            )

    def tokens(self, value, credentials):
        access, refresh = value["access_token"], value["refresh_token"]
        if not all(isinstance(x, str) and 1 <= len(x) <= 4000 for x in (access, refresh)):
            raise ValueError("Invalid authorization response")
        expires = int(value["expires_in"])
        if not 0 < expires <= 366 * 86400:
            raise ValueError("Invalid token expiry")
        return {
            **credentials,
            "token": access,
            "refresh_token": refresh,
            "expires_at": self.feeds.clock() + expires,
        }

    def action(self, data):
        with self.lock:
            now = self.feeds.clock()
            if data.get("action") == "start" and set(data) == {
                "action",
                "client_id",
                "client_secret",
            }:
                if any(
                    not isinstance(data[k], str)
                    or not (1 if k == "client_id" else 0) <= len(data[k]) <= 4000
                    or "\n" in data[k]
                    or "\r" in data[k]
                    for k in ("client_id", "client_secret")
                ):
                    raise ValueError("Supply private application credentials")
                with self.feeds.store() as store:
                    old = preference(store, SYSTEM, "feed_connection.trakt", {})
                    setup = preference(store, SYSTEM, KEY, {})
                    if not setup.get("profile"):
                        raise ValueError("Save private setup first")
                value = self.call("device/code", {"client_id": data["client_id"]})
                interval = max(5, min(60, int(value["interval"])))
                expires = min(1800, int(value["expires_in"]))
                if (
                    expires <= 0
                    or not isinstance(value["device_code"], str)
                    or len(value["device_code"]) > 4000
                ):
                    raise ValueError("Invalid device response")
                self.pending = {
                    "old": old,
                    "setup": setup,
                    "credentials": {k: data[k] for k in ("client_id", "client_secret") if data[k]},
                    "device_code": value["device_code"],
                    "next": now + interval,
                    "interval": interval,
                    "expires": now + expires,
                }
                # Fixed provider link, never render an upstream URL as a navigation target.
                return {
                    "state": "awaiting_approval",
                    "user_code": str(value["user_code"])[:40],
                    "verification_url": "https://trakt.tv/activate",
                    "interval": interval,
                }
            if data != {"action": "check"}:
                raise ValueError("Choose start or check")
            pending = self.pending
            if not pending or now >= pending["expires"]:
                self.pending = None
                return {"state": "expired_restart_sign_in"}
            if now < pending["next"]:
                return {"state": "awaiting_approval"}
            pending["next"] = now + pending["interval"]
            try:
                value = self.call(
                    "device/token", {**pending["credentials"], "code": pending["device_code"]}
                )
            except HTTPError as error:
                if error.code in (400, 429):
                    if error.code == 429:
                        pending["interval"] = min(60, pending["interval"] + 5)
                        try:
                            retry_after = int(error.headers.get("Retry-After", 0))
                        except (AttributeError, TypeError, ValueError):
                            retry_after = 0
                        pending["next"] = now + max(pending["interval"], retry_after)
                    return {"state": "awaiting_approval"}
                self.pending = None
                return {"state": "authorization_failed_restart"}
            with self.feeds.store() as store:
                if preference(store, SYSTEM, KEY, {}) != pending["setup"]:
                    self.pending = None
                    raise ValueError("Private setup changed; authorize again")
            new = self.tokens(value, pending["credentials"])
            self.pending = None
            self.save(pending["old"], new)
            self.feeds.next_poll.pop("watch_history", None)
            return {"state": "authorized_enable_feed_to_collect"}

    def refresh(self, connection):
        if connection.get("reauthorize_required"):
            raise ValueError("Authorize Trakt again")
        if (
            not connection.get("refresh_token")
            or connection.get("expires_at", 0) > self.feeds.clock() + 120
        ):
            return connection
        with self.lock:
            with self.feeds.store() as store:
                current = preference(store, SYSTEM, "feed_connection.trakt", {})
            if current != connection:
                return current
            try:
                value = self.call(
                    "token",
                    {
                        "refresh_token": connection["refresh_token"],
                        "client_id": connection["client_id"],
                        **(
                            {"client_secret": connection["client_secret"]}
                            if connection.get("client_secret")
                            else {}
                        ),
                        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                        "grant_type": "refresh_token",
                    },
                )
                new = self.tokens(
                    value,
                    {k: connection[k] for k in ("client_id", "client_secret") if connection.get(k)},
                )
            except Exception:
                # Single-use refresh may have succeeded remotely before transport loss.
                # Never replay that token automatically after an uncertain outcome.
                self.save(connection, {**connection, "reauthorize_required": True})
                raise ValueError("Authorize Trakt again") from None
            self.save(connection, new)
            return new

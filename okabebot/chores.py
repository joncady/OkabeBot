"""Explicit private recurring chores; current state, no passive completion inference."""

from contextlib import closing
import json
from pathlib import Path
import re
import time
import uuid
from .amadeus import Store
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY

PREFIX = "chores.item."
MAX_CHORES = 100


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Choose a saved chore")
    return value


class Chores:
    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = Path(folder), clock

    def store(self):
        return closing(Store(self.folder, clock=self.clock))

    def setup(self, store, required=False):
        setup = preference(store, SYSTEM, KEY, {})
        if required and not setup.get("profile"):
            raise ValueError("Finish private Amadeus setup before creating chores")
        return setup

    def values(self, store, profile):
        return [
            json.loads(row[0])
            for row in store.db.execute(
                "SELECT value FROM preferences WHERE subject=? AND key LIKE ? ORDER BY key",
                (profile, PREFIX + "%"),
            )
        ]

    def item(self, store, profile, chore_id):
        return preference(store, profile, PREFIX + identity(chore_id), {})

    def public(self, value):
        value = {k: v for k, v in value.items() if k not in ("completion_ids", "last_delivery_id")}
        value["overdue"] = bool(
            value["enabled"]
            and value["due_at"] <= self.clock()
            and value.get("snoozed_until", 0) <= self.clock()
        )
        return value

    def snapshot(self):
        with self.store() as store:
            setup = self.setup(store)
            items = self.values(store, setup["profile"]) if setup.get("profile") else []
        return {
            "items": [
                self.public(v)
                for v in sorted(items, key=lambda v: (not v["enabled"], v["due_at"], v["id"]))
            ],
            "setup_required": not bool(setup.get("profile")),
            "paused": bool(setup.get("paused")),
            "guest": bool(setup.get("guest")),
        }

    def response(self, item):
        value = self.snapshot()
        current = next(
            (
                v
                for v in value["items"]
                if v["id"] == item["id"] and v["revision"] == item["revision"]
            ),
            None,
        )
        return {
            **value,
            "item": current,
            **({"state": "context_changed"} if current is None else {}),
        }

    def save(self, data):
        fields = {"title", "interval_days", "repeat_days", "enabled"}
        if not isinstance(data, dict) or not fields <= set(data) or set(data) - fields - {"id"}:
            raise ValueError("Choose title, delay, repeat interval and enabled state")
        title = data["title"]
        if (
            not isinstance(title, str)
            or not 1 <= len(title.strip()) <= 120
            or any(ord(c) < 32 for c in title)
        ):
            raise ValueError("Use a chore title of 1–120 characters")
        if type(data["enabled"]) is not bool:
            raise ValueError("Choose enabled or disabled")
        for key, maximum in (("interval_days", 365), ("repeat_days", 30)):
            if type(data[key]) is not int or not 1 <= data[key] <= maximum:
                raise ValueError("Choose a valid day interval")
        chore_id = identity(data["id"]) if data.get("id") else uuid.uuid4().hex
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = self.setup(store, True)
            profile = setup["profile"]
            old = self.item(store, profile, chore_id)
            if not old and len(self.values(store, profile)) >= MAX_CHORES:
                raise ValueError("At most 100 configured chores")
            edit = {k: data[k] for k in fields}
            edit["title"] = title.strip()
            if old and all(old[k] == v for k, v in edit.items()):
                item = old
            else:
                now = self.clock()
                item = {
                    "id": chore_id,
                    "created_at": now,
                    "last_done_at": None,
                    "last_reminded_at": None,
                    "snoozed_until": 0,
                    "completion_ids": [],
                    **old,
                    **edit,
                    "revision": uuid.uuid4().hex,
                }
                anchor = (
                    item["last_done_at"] if item["last_done_at"] is not None else item["created_at"]
                )
                item["due_at"] = anchor + item["interval_days"] * 86400
                store.remember(profile, PREFIX + chore_id, item)
        return self.response(item)

    def complete(self, chore_id, request_id=None):
        identity(chore_id)
        request_id = request_id or uuid.uuid4().hex
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_.:-]{1,160}", request_id
        ):
            raise ValueError("Invalid completion request")
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = self.setup(store, True)
            item = self.item(store, setup["profile"], chore_id)
            if not item:
                raise ValueError("Chore is no longer configured")
            now = self.clock()
            if request_id not in item.get("completion_ids", []) and not (
                item.get("last_done_at") is not None and 0 <= now - item["last_done_at"] < 3
            ):
                item.update(
                    last_done_at=now,
                    due_at=now + item["interval_days"] * 86400,
                    snoozed_until=0,
                    last_reminded_at=None,
                    revision=uuid.uuid4().hex,
                    completion_ids=(item.get("completion_ids", []) + [request_id])[-8:],
                )
                item.pop("last_delivery_id", None)
                store.remember(setup["profile"], PREFIX + chore_id, item)
        return self.response(item)

    def remove(self, chore_id):
        identity(chore_id)
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = self.setup(store, True)
            store.db.execute(
                "DELETE FROM preferences WHERE subject=? AND key=?",
                (setup["profile"], PREFIX + chore_id),
            )
        return self.snapshot()

    def snooze(self, chore_id, days):
        if type(days) is not int or not 1 <= days <= 30:
            raise ValueError("Snooze for 1–30 days")
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = self.setup(store, True)
            item = self.item(store, setup["profile"], chore_id)
            if not item:
                raise ValueError("Chore is no longer configured")
            item.update(snoozed_until=self.clock() + days * 86400, revision=uuid.uuid4().hex)
            store.remember(setup["profile"], PREFIX + chore_id, item)
        return self.snapshot()

    def due(self, remind_only=False, limit=3):
        with self.store() as store:
            return self.due_from_store(store, remind_only=remind_only, limit=limit)

    def due_from_store(self, store, remind_only=False, limit=3):
        """Use an existing transaction when coordinating reminder/session claims."""
        if type(limit) is not int or not 1 <= limit <= MAX_CHORES:
            raise ValueError("Choose a bounded chore count")
        setup = self.setup(store)
        if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
            return []
        items = self.values(store, setup["profile"])
        now = self.clock()
        items = [
            v
            for v in items
            if v["enabled"]
            and v["due_at"] <= now
            and v.get("snoozed_until", 0) <= now
            and (
                not remind_only
                or v.get("last_reminded_at") is None
                or now - v["last_reminded_at"] >= v["repeat_days"] * 86400
            )
        ]
        return [
            self.public(v)
            for v in sorted(
                items, key=lambda v: (v.get("last_reminded_at") or 0, v["due_at"], v["id"])
            )[:limit]
        ]

    def context(self, include_upcoming=False):
        """Permission-gated model/tool projection; operational replay IDs stay private."""
        if type(include_upcoming) is not bool:
            raise ValueError("Choose whether to include upcoming chores")
        with self.store() as store:
            setup = self.setup(store)
            if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
                return {"state": "paused_or_not_configured", "items": []}
            values = (
                self.values(store, setup["profile"])
                if include_upcoming
                else self.due_from_store(store, limit=MAX_CHORES)
            )
        items = [
            {
                key: value.get(key)
                for key in (
                    "id",
                    "title",
                    "due_at",
                    "last_done_at",
                    "interval_days",
                    "repeat_days",
                    "enabled",
                    "snoozed_until",
                )
            }
            for value in values
        ]
        return {
            "items": items,
            "scope": "Explicit configured chore records only. A scan or dashboard action records completion; do not infer who did it or treat reminders as completion. Last done is the latest recorded completion, not a full activity history. No changes were made.",
        }

    def still_due(self, chore_id, due_at=None, revision=None):
        for item in self.due(limit=MAX_CHORES):
            if (
                item["id"] == chore_id
                and (due_at is None or item["due_at"] == due_at)
                and (revision is None or item["revision"] == revision)
            ):
                return item
        return None

    def claim_reminder(
        self, chore_id, delivery_id, channel, expected_due_at=None, expected_revision=None
    ):
        """Acknowledge successful delivery only, never called by preview/read polling."""
        identity(chore_id)
        if (
            channel not in ("morning", "proactive")
            or not isinstance(delivery_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", delivery_id)
        ):
            raise ValueError("Use a bounded reminder delivery identity")
        with self.store() as store, store.db:
            store.db.execute("BEGIN IMMEDIATE")
            setup = self.setup(store)
            if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
                return False
            item = self.item(store, setup["profile"], chore_id)
            now = self.clock()
            if (
                not item
                or not item["enabled"]
                or item["due_at"] > now
                or item.get("snoozed_until", 0) > now
            ):
                return False
            if expected_due_at is not None and item["due_at"] != expected_due_at:
                return False
            if expected_revision is not None and item["revision"] != expected_revision:
                return False
            if item.get("last_delivery_id") == delivery_id:
                return False
            if (
                item.get("last_reminded_at") is not None
                and now - item["last_reminded_at"] < item["repeat_days"] * 86400
            ):
                return False
            item.update(
                last_reminded_at=now, last_delivery_id=delivery_id, last_reminder_channel=channel
            )
            store.remember(setup["profile"], PREFIX + chore_id, item)
        return True

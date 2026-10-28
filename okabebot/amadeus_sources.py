"""Permission-gated shadow metadata adapters. Never predicts, speaks or acts."""

import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from .amadeus import Store
from .amadeus_onboarding import SYSTEM, KEY


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def text(value):
    return "".join(c for c in str(value or "") if ord(c) >= 32)[:512]


class Collector:
    def __init__(self, folder, *, clock=time.time):
        self.folder, self.clock = Path(folder), clock

    def _record(self, source, build):
        store = None
        try:
            store = Store(self.folder, sources=[source], clock=self.clock)
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                setting = next(
                    (p["value"] for p in store.recall(SYSTEM)["preferences"] if p["key"] == KEY),
                    None,
                )
                if not isinstance(setting, dict) or setting.get("paused") is not False:
                    return {"state": "paused"}
                if setting.get("guest") is not False or source not in setting.get("sources", []):
                    return {"state": "not_permitted"}
                rows = build(setting)
                if not rows:
                    return {"state": "no_metadata"}
                # One record per transaction: pause/forget serialize with ingestion.
                if len(rows) != 1:
                    raise ValueError("Use one bounded observation")
                kind, payload, scope, event_id, observed = rows[0]
                store.retention = setting["retention_days"] * 86400
                result = store.observe(
                    source=source,
                    external_id=event_id,
                    subject=setting["profile"] if scope == "profile" else "unknown",
                    kind=kind,
                    payload=payload,
                    observed_at=observed,
                )
                return {"state": result["status"]}
        except Exception:
            # Never leak payloads, titles, entity names or feed addresses to logs.
            return {"state": "unavailable"}
        finally:
            if store is not None:
                store.close()

    def media(self, video):
        def build(_):
            if hasattr(video, "video"):
                value = video.video
                if not value:
                    music = video.music
                    value = dict(
                        music,
                        app="Spotify",
                        state="PLAYING" if music.get("is_playing") else "PAUSED",
                    )
            else:
                value = video
            if not isinstance(value, dict) or not value.get("title") or not value.get("app"):
                return []
            updated = value.get("updated_at")
            if type(updated) not in (int, float) or not 0 <= self.clock() - updated <= 120:
                return []
            state = value.get("state")
            if state not in ("PLAYING", "PAUSED", "IDLE", "BUFFERING", "UNKNOWN"):
                return []
            payload = {"app": text(value["app"]), "title": text(value["title"]), "state": state}
            if value.get("content_id"):
                payload["content_id"] = digest(str(value["content_id"]))
            if (
                type(value.get("duration")) in (int, float)
                and math.isfinite(value["duration"])
                and value["duration"] >= 0
            ):
                payload["duration_s"] = value["duration"]
            # Checkpoints are approximate observation, never completion/liking proof.
            bucket = int(self.clock() // 300)
            return [("media", payload, "household", digest([payload, bucket]), None)]

        return self._record("media", build)

    def interaction(self, kind):
        if kind not in ("user", "turn_completed"):
            return {"state": "ignored"}
        payload = {
            "action": "question_submitted" if kind == "user" else "turn_finished",
            "surface": "controller",
        }
        return self._record(
            "interaction", lambda _: [("interaction", payload, "household", uuid.uuid4().hex, None)]
        )

    def calendar(self, state):
        try:
            return self._calendar(state)
        except Exception:
            return {"state": "unavailable"}

    def _calendar(self, state):
        checked = state.get("calendar_checked_at")
        if type(checked) not in (int, float) or not 0 <= self.clock() - checked <= 300:
            return {"state": "stale"}
        upcoming = state.get("calendar_upcoming")
        if not isinstance(upcoming, list) or len(upcoming) > 200:
            return {"state": "unavailable"}
        records = []
        for item in upcoming:
            start = item.get("start")
            if type(start) not in (int, float) or not math.isfinite(start) or start <= checked:
                continue
            records.append(
                {
                    "event_id": digest([item.get("title"), start]),
                    "summary": text(item.get("title")),
                    "start_at": start,
                }
            )
        snapshot_id = digest([records, int(checked // 300)])
        for payload in records:
            payload["snapshot_id"] = snapshot_id
            result = self._record(
                "calendar", lambda _, p=payload: [("calendar", p, "profile", digest(p), None)]
            )
            if result["state"] not in ("stored", "duplicate"):
                return result
        marker = {
            "snapshot_id": snapshot_id,
            "event_count": len(records),
            "start_at": checked,
            "end_at": checked + 2 * 86400,
        }
        # Mark completeness only after every permitted record was stored.
        # Include checked time in the marker ID to avoid conflicting stable IDs.
        return self._record(
            "calendar", lambda _: [("calendar_snapshot", marker, "profile", digest(marker), None)]
        )

    def home_assistant(self, data):
        if not isinstance(data, dict) or set(data) != {
            "entity_id",
            "state",
            "event_id",
            "observed_at",
        }:
            raise ValueError("Invalid source envelope")
        observed = data["observed_at"]
        if type(observed) not in (int, float) or not 0 <= self.clock() - observed <= 60:
            raise ValueError("Stale source event")
        if not isinstance(data["event_id"], str) or not 1 <= len(data["event_id"]) <= 128:
            raise ValueError("Invalid event ID")
        if not isinstance(data["entity_id"], str) or not isinstance(data["state"], str):
            raise ValueError("Use bounded source strings")
        if len(data["entity_id"]) > 200 or len(data["state"]) > 100:
            raise ValueError("Source field too long")
        bindings = json.loads((self.folder / "ha-bindings.json").read_text())
        entity = data["entity_id"]
        if entity in bindings.get("door", []):
            kind = "door"
            state = {
                "on": "open",
                "off": "closed",
                "unknown": "unknown",
                "unavailable": "unknown",
            }.get(data["state"])
        elif entity in bindings.get("presence", []):
            kind = "presence"
            state = {
                "home": "home",
                "not_home": "away",
                "unknown": "unknown",
                "unavailable": "unknown",
            }.get(data["state"], "unknown")
        else:
            raise PermissionError("Unbound source entity")
        if state is None:
            raise ValueError("Invalid source state")
        return self._record(
            "door_presence",
            lambda _: [
                (
                    kind,
                    {"state": state},
                    "household",
                    digest([entity, data["event_id"], kind]),
                    observed,
                )
            ],
        )

    def maintain(self):
        # Called periodically even while paused; expiry is independent of consent.
        store = Store(self.folder, clock=self.clock)
        try:
            store.prune()
        finally:
            store.close()

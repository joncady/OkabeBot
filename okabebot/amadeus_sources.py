"""Permission-gated shadow metadata adapters. Never predicts, speaks or acts."""

from datetime import datetime
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
            if not isinstance(value, dict) or not value.get("app"):
                return []
            updated = value.get("updated_at")
            if type(updated) not in (int, float) or not 0 <= self.clock() - updated <= 120:
                return []
            state = value.get("state")
            if state not in ("PLAYING", "PAUSED", "IDLE", "BUFFERING", "UNKNOWN"):
                return []
            # Receivers commonly clear the title on STOP. Dropping that observation
            # leaves a false PLAYING tail and hides the next actual session start.
            if not value.get("title") and state not in ("IDLE", "UNKNOWN"):
                return []
            payload = {"app": text(value["app"]), "state": state}
            if "device_id" in value:
                endpoint = value["device_id"]
                if not isinstance(endpoint, str) or not 1 <= len(endpoint) <= 200:
                    raise ValueError("Use a bounded media endpoint")
                payload["device_id"] = digest(endpoint)
            if value.get("title"):
                payload["title"] = text(value["title"])
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
        upcoming = state.get("calendar_context", state.get("calendar_upcoming"))
        if not isinstance(upcoming, list) or len(upcoming) > 200:
            return {"state": "unavailable"}
        records = []
        busy_complete = state.get("calendar_busy_complete") is True
        for item in upcoming:
            start, end = item.get("start"), item.get("end")
            if type(start) not in (int, float) or not math.isfinite(start):
                busy_complete = False
                continue
            valid_end = type(end) in (int, float) and math.isfinite(end) and end > start
            if not valid_end or type(item.get("busy")) is not bool:
                busy_complete = False
            if start <= checked and not (valid_end and end > checked):
                continue
            payload = {
                "event_id": digest([item.get("title"), start]),
                "summary": text(item.get("title")),
                "start_at": start,
            }
            if valid_end:
                payload["end_at"] = end
            if type(item.get("busy")) is bool:
                payload["busy"] = "busy" if item["busy"] else "free"
            if type(item.get("all_day")) is bool:
                payload["all_day"] = "yes" if item["all_day"] else "no"
            records.append(payload)
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
            "busy_coverage": "complete" if busy_complete else "partial",
        }
        # Mark completeness only after every permitted record was stored.
        # Include checked time in the marker ID to avoid conflicting stable IDs.
        return self._record(
            "calendar", lambda _: [("calendar_snapshot", marker, "profile", digest(marker), None)]
        )

    def availability(self, data):
        expected = {"entity_id", "state", "event_id", "observed_at"}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError("Invalid availability envelope")
        if (
            not isinstance(data["entity_id"], str)
            or not 1 <= len(data["entity_id"]) <= 200
            or not isinstance(data["event_id"], str)
            or not 1 <= len(data["event_id"]) <= 128
        ):
            raise ValueError("Use bounded availability identifiers")
        if (
            type(data["observed_at"]) not in (int, float)
            or not 0 <= self.clock() - data["observed_at"] <= 60
        ):
            raise ValueError("Stale availability")
        if data["state"] not in ("on", "off", "unknown", "unavailable"):
            raise ValueError("Use normalized coarse availability states")
        bindings = json.loads((self.folder / "ha-bindings.json").read_text()).get(
            "availability", {}
        )
        signal = next(
            (
                k
                for k in ("dnd", "focus", "charging", "room")
                if data["entity_id"] in bindings.get(k, [])
            ),
            None,
        )
        if not signal:
            raise PermissionError("Unbound availability source")
        payload = {
            "signal": signal,
            "state": "unknown" if data["state"] == "unavailable" else data["state"],
            "device_id": digest(data["entity_id"]),
            "observation": "snapshot" if data["event_id"].startswith("snapshot:") else "change",
        }
        return self._record(
            "availability",
            lambda _: [
                (
                    "availability",
                    payload,
                    "household" if signal == "room" else "profile",
                    digest([data["entity_id"], data["event_id"]]),
                    data["observed_at"],
                )
            ],
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
        source = "door_presence"
        # Timestamp entities survive reconnects. Deduplicate by the actual
        # occurrence, never by HA's reconnect context or receipt time.
        ring = bindings.get("ring", {})
        if entity in ring:
            category = ring[entity]
            if category not in ("motion", "doorbell", "activity"):
                raise ValueError("Unsupported Ring category")
            try:
                occurrence = datetime.fromisoformat(data["state"].replace("Z", "+00:00"))
                if occurrence.tzinfo is None:
                    raise ValueError("Ring timestamp needs timezone")
                occurred = occurrence.timestamp()
            except ValueError:
                return {"state": "no_metadata"}
            if not 0 <= self.clock() - occurred <= 300:
                return {"state": "no_metadata"}
            return self._record(
                source,
                lambda _: [
                    (
                        "household_event",
                        {
                            "provider": "Ring",
                            "event": category,
                            "detail": "Front door " + category + " detected",
                            "provenance": "sensor",
                        },
                        "household",
                        digest([entity, occurred, category]),
                        occurred,
                    )
                ],
            )
        if entity in bindings.get("tv", []):
            state = data["state"]
            if state in ("unknown", "unavailable"):
                state = "unknown"
            if state not in (
                "on",
                "off",
                "standby",
                "playing",
                "paused",
                "idle",
                "buffering",
                "unknown",
            ):
                raise ValueError("Invalid TV state")
            return self._record(
                "tv_usage",
                lambda _: [
                    (
                        "tv_state",
                        {
                            "state": state,
                            "device_id": digest(entity),
                            "observation": "snapshot"
                            if data["event_id"].startswith("snapshot:")
                            else "change",
                        },
                        "household",
                        digest([entity, data["event_id"], "tv_state"]),
                        observed,
                    )
                ],
            )
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
            source,
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

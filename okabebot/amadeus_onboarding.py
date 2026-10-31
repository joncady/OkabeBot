"""Owner-only private setup and memory controls; never starts a collector."""

import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .amadeus import Store, identifier
from .amadeus_coaching import Coaching, TOPICS
from .adapters.context import FEEDS


SYSTEM = "amadeus-system"
KEY = "onboarding"

SOURCES = {
    **{feed.id: feed.label for feed in FEEDS.values()},
    "availability": "Selected DND/focus, charging and shared-room occupancy states (separate opt-in)",
    "tv_usage": "TV power/state snapshots (household context; no titles or viewer identity)",
    "phone_context": "Phone screen on/off and next-alarm time (no location, apps or health)",
    "weather": "Outdoor weather condition and temperature",
    "door_presence": "Door and presence metadata",
    "calendar": "Calendar event metadata",
    "media": "Media playback metadata",
    "interaction": "Companion interaction metadata (no transcript or audio)",
}


def validate(value):
    expected = {
        "profile",
        "sources",
        "retention_days",
        "timezone",
        "quiet_start",
        "quiet_end",
        "coaching_choice",
        "coaching_topics",
        "coaching_mode",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Provide the setup fields")
    identifier(value["profile"])
    if value["profile"] in (SYSTEM, "unknown"):
        raise ValueError("Choose a private profile identifier")
    if not isinstance(value["sources"], list) or any(
        not isinstance(s, str) or s not in SOURCES for s in value["sources"]
    ):
        raise ValueError("Choose supported observation sources")
    if type(value["retention_days"]) is not int or not 1 <= value["retention_days"] <= 365:
        raise ValueError("Retention must be 1–365 days")
    try:
        if not isinstance(value["timezone"], str):
            raise ValueError("Choose an IANA timezone")
        ZoneInfo(value["timezone"])
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("Choose an IANA timezone") from None
    for key in ("quiet_start", "quiet_end"):
        if not isinstance(value[key], str) or not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", value[key]
        ):
            raise ValueError("Use HH:MM quiet times")
    if value["coaching_mode"] not in ("establish", "reaffirm"):
        raise ValueError("Choose establish or reaffirm")
    choice, topics = value["coaching_choice"], value["coaching_topics"]
    if choice not in ("choose_topics", "not_now", "no"):
        raise ValueError("Choose whether coaching is welcome")
    if not isinstance(topics, list) or any(
        not isinstance(t, str) or t not in TOPICS for t in topics
    ):
        raise ValueError("Choose supported coaching topics")
    if (choice == "choose_topics") != bool(topics):
        raise ValueError("Choose topics to opt in; declines cannot contain topics")
    return dict(value, sources=sorted(set(value["sources"])), coaching_topics=sorted(set(topics)))


class Onboarding:
    def __init__(self, folder):
        from pathlib import Path

        self.folder = Path(folder)
        self.store = Store(folder)

    def close(self):
        self.store.close()

    def settings(self):
        return next(
            (p["value"] for p in self.store.recall(SYSTEM)["preferences"] if p["key"] == KEY), None
        )

    def snapshot(self):
        value = self.settings()
        draft = next(
            (p["value"] for p in self.store.recall(SYSTEM)["preferences"] if p["key"] == "draft"),
            {},
        )
        return {
            "settings": value,
            "draft": draft if value is None else {},
            "sources": SOURCES,
            "coaching_topics": TOPICS,
            "collection_available": True,
            "collection_active": bool(
                value
                and value.get("paused") is False
                and value.get("guest") is False
                and value.get("sources")
            ),
            "collection_mode": "shadow_metadata",
            "nudges_active": False,
            "profile_scope": "single_private_profile",
        }

    def save(self, data):
        value = validate(data)
        previous = self.settings()
        if previous and previous["profile"] != value["profile"]:
            raise ValueError("Forget Amadeus data before changing the profile identifier")
        profile = value["profile"]
        # Validate everything before mutation. A temporary transaction is not an
        # authorization to activate any source, inference or delivery worker.
        coaching = {
            "version": 1,
            "choice": value["coaching_choice"],
            "enabled": value["coaching_choice"] == "choose_topics",
            "topics": value["coaching_topics"],
            "paused_until": 0,
        }
        value.update(
            paused=previous.get("paused", True) if previous else True,
            guest=previous.get("guest", False) if previous else False,
        )
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            if self.settings() != previous:
                raise ValueError("Setup changed; reload before saving")
            if previous and all(
                previous[k] == value[k] for k in ("coaching_choice", "coaching_topics")
            ):
                latest = next(
                    (
                        p["value"]
                        for p in self.store.recall(profile)["preferences"]
                        if p["key"] == "health.coaching"
                    ),
                    None,
                )
                if latest is not None:
                    # Saving unrelated fields cannot undo stop/snooze feedback.
                    coaching = latest
            for subject, key, item in (
                (SYSTEM, KEY, value),
                (profile, "health.coaching", coaching),
            ):
                self.store.db.execute(
                    "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) "
                    "DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (subject, key, json.dumps(item, allow_nan=False), self.store.clock()),
                )
            self.store.db.execute(
                "UPDATE events SET expires_at=MIN(expires_at,observed_at+?)",
                (value["retention_days"] * 86400,),
            )
            from .context_records import clear, prune

            for table, origin in (
                ("context_records", "last_seen"),
                ("context_changes", "observed_at"),
                ("context_signal_buckets", "bucket"),
                ("context_feed_status", "checked_at"),
            ):
                if self.store.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name=?", (table,)
                ).fetchone():
                    self.store.db.execute(
                        "UPDATE " + table + " SET expires_at=MIN(expires_at," + origin + "+?)",
                        (value["retention_days"] * 86400,),
                    )
            if previous:
                for revoked in set(previous.get("sources", [])) - set(value["sources"]):
                    clear(self.store.db, source=revoked)
            prune(self.store.db, self.store.clock())
            self.store.db.execute("DELETE FROM events WHERE expires_at<=?", (self.store.clock(),))
            if self.store.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shadow_decisions'"
            ).fetchone():
                self.store.db.execute(
                    "DELETE FROM shadow_decisions WHERE evaluated_at<?",
                    (self.store.clock() - min(7, value["retention_days"]) * 86400,),
                )
                if previous and set(previous.get("sources", [])) - set(value["sources"]):
                    self.store.db.execute(
                        "DELETE FROM shadow_decisions WHERE subject=?", (profile,)
                    )
            if previous and set(previous.get("sources", [])) - set(value["sources"]):
                # Revocation invalidates derived opportunity state; adding a source
                # later cannot silently resume an old personalized context trial.
                self.store.db.execute(
                    "DELETE FROM preferences WHERE subject=? AND key='context.enabled'", (profile,)
                )
                if self.store.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='context_exposures'"
                ).fetchone():
                    self.store.db.execute(
                        "DELETE FROM context_exposures WHERE subject=?", (profile,)
                    )
            self.store.db.execute(
                "DELETE FROM preferences WHERE subject=? AND key='draft'", (SYSTEM,)
            )
        return self.snapshot()

    def subject(self):
        value = self.settings()
        if not value:
            raise ValueError("Save setup choices first")
        return value["profile"]

    def memory(self):
        return dict(
            self.store.recall(self.subject()),
            household_events=[
                dict(row, payload=json.loads(row["payload"]))
                for row in self.store.db.execute(
                    "SELECT * FROM events WHERE subject IN ('unknown','household') AND expires_at>? "
                    "ORDER BY observed_at DESC,id LIMIT 20",
                    (self.store.clock(),),
                )
            ],
        )

    def export(self):
        from .context_records import export

        result = self.memory()
        result.update(export(self.store, self.subject()))
        from .kitchen import export as kitchen_export

        result["kitchen"] = kitchen_export(self.store, self.subject())
        rows = self.store.db.execute(
            "SELECT * FROM events WHERE subject=? AND expires_at>? ORDER BY observed_at,id",
            (self.subject(), self.store.clock()),
        ).fetchall()
        result["events"] = [dict(row, payload=json.loads(row["payload"])) for row in rows]
        rows = self.store.db.execute(
            "SELECT * FROM events WHERE subject IN ('unknown','household') AND expires_at>? ORDER BY observed_at,id",
            (self.store.clock(),),
        ).fetchall()
        result["household_events"] = [dict(row, payload=json.loads(row["payload"])) for row in rows]
        from .presence_control import read

        result["text_feedback"] = read(self.folder / "text-feedback.json", {}).get("items", [])[
            -100:
        ]
        return dict(
            result, setup=self.settings(), export_scope="profile_and_unattributed_household"
        )

    def control(self, data):
        if not isinstance(data, dict) or not data or set(data) - {"paused", "guest"}:
            raise ValueError("Choose pause or guest mode")
        if any(type(v) is not bool for v in data.values()):
            raise ValueError("Controls must be boolean")
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            value = self.settings()
            if not value:
                raise ValueError("Save setup choices first")
            value.update(data)
            self.store.remember(SYSTEM, KEY, value)
        return self.snapshot()

    def preference(self, data):
        if not isinstance(data, dict) or set(data) != {"key", "value"}:
            raise ValueError("Provide preference key and JSON value")
        key = identifier(data["key"])
        if not key.startswith("user."):
            raise ValueError("User preference keys must start with user.")
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            self.store.remember(self.subject(), key, data["value"])
        return self.memory()

    def forget(self, data):
        if data == {"confirm": "forget_amadeus"}:
            with self.store.db:
                from .context_records import clear

                clear(self.store.db)
                from .kitchen import clear as clear_kitchen

                clear_kitchen(self.store.db)
                self.store.db.execute("DELETE FROM events")
                self.store.db.execute("DELETE FROM preferences")
                # Feedback contains private conversation excerpts, not integration settings.
                (self.folder / "text-feedback.json").unlink(missing_ok=True)
                (self.folder / "prompt-treatments.json").unlink(missing_ok=True)
                if self.store.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shadow_decisions'"
                ).fetchone():
                    self.store.db.execute("DELETE FROM shadow_decisions")
                if self.store.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='context_exposures'"
                ).fetchone():
                    self.store.db.execute("DELETE FROM context_exposures")
            return self.snapshot()
        if not isinstance(data, dict) or set(data) != {"key"}:
            raise ValueError("Confirm deletion or provide a preference key")
        key = identifier(data["key"])
        if not key.startswith("user.") and key != "context.preferences":
            raise ValueError("Use the coaching controls to change coaching consent")
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            self.store.forget(self.subject(), key=key)
            if key == "context.preferences":
                self.store.forget(self.subject(), key="conversation.preference_recency")
                self.store.forget(self.subject(), key="conversation.last_memory")
                self.store.remember(self.subject(), "conversation.suggestion_legacy_disabled", True)
                for metadata in (
                    "conversation.topic_recency",
                    "conversation.topic_feedback",
                    "conversation.suggestions",
                    "conversation.feedback_pause",
                ):
                    self.store.forget(self.subject(), key=metadata)
            if (
                key == "context.preferences"
                and self.store.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shadow_decisions'"
                ).fetchone()
            ):
                self.store.db.execute(
                    "DELETE FROM shadow_decisions WHERE subject=?", (self.subject(),)
                )
        return self.memory()

    def feedback(self, data):
        if not isinstance(data, dict) or set(data) - {"outcome", "topic"}:
            raise ValueError("Provide explicit feedback")
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            Coaching(self.store).feedback(
                self.subject(), data.get("outcome"), topic=data.get("topic")
            )
        return self.memory()

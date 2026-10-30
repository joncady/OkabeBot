"""Grounded opt-in household suggestions; no identity inference or device controls."""

import hashlib
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .amadeus import encode
from .amadeus_habits import preference
from .amadeus_onboarding import KEY, SYSTEM
from .amadeus_feeds import context

CONFIG = "household_nudges.config"
EVIDENCE = "household_nudges.evidence"
DELIVERY = "household_nudges.delivery"
DEFAULTS = dict(
    enabled=False,
    departure_enabled=True,
    departure_away_minutes=10,
    bedtime_enabled=True,
    bedtime_start="21:00",
    bedtime_end="23:00",
    comfort_enabled=True,
    cold_c=18,
    hot_c=27,
    comfort_hold_minutes=15,
    cooldown_hours=12,
)


def configure(store, data):
    if not isinstance(data, dict) or set(data) != set(DEFAULTS):
        raise ValueError("Provide household nudge choices")
    for key in ("enabled", "departure_enabled", "bedtime_enabled", "comfort_enabled"):
        if type(data[key]) is not bool:
            raise ValueError("Choose household nudge enablement")
    for key, low, high in (
        ("departure_away_minutes", 1, 120),
        ("cold_c", 5, 25),
        ("hot_c", 20, 40),
        ("comfort_hold_minutes", 1, 120),
        ("cooldown_hours", 1, 72),
    ):
        if type(data[key]) is not int or not low <= data[key] <= high:
            raise ValueError("Household threshold outside supported range")
    if data["cold_c"] >= data["hot_c"]:
        raise ValueError("Cold threshold must be below hot threshold")
    for key in ("bedtime_start", "bedtime_end"):
        if not isinstance(data[key], str) or not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", data[key]
        ):
            raise ValueError("Choose a valid local bedtime window")
    if data["bedtime_start"] == data["bedtime_end"]:
        raise ValueError("Choose a bounded bedtime window")
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        setup = preference(store, SYSTEM, KEY, {})
        if not setup.get("profile"):
            raise ValueError("Save private setup first")
        profile = setup["profile"]
        store.db.executemany(
            "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            [
                (profile, CONFIG, encode(data), store.clock()),
                (profile, EVIDENCE, encode({}), store.clock()),
            ],
        )
    return data


def label(item):
    return " ".join(re.sub(r"[<>{}]", " ", str(item.get("label", "device"))).split())[:45]


def _home(home, expected):
    scanners = home.get("healthy_scanners", 0)
    anchors = home.get("follow_destinations", [])
    required = (
        len(set(anchors))
        if isinstance(anchors, list) and all(isinstance(a, str) for a in anchors)
        else 0
    )
    return bool(
        home.get("configured")
        and home.get("fresh")
        and type(scanners) is int
        and required > 0
        and scanners >= required
        and home.get("presence") in expected
    )


class HouseholdNudges:
    def __init__(self, store, home=None):
        self.store, self.home = store, home or {}

    def snapshot(self, *, update=False):
        s = self.store
        setup = preference(s, SYSTEM, KEY, {})
        profile = setup.get("profile", SYSTEM)
        cfg = {**DEFAULTS, **preference(s, profile, CONFIG, {})}
        result = {"config": cfg, "preview": [], "state": "disabled"}
        if (
            not cfg["enabled"]
            or not setup.get("profile")
            or setup.get("paused")
            or setup.get("guest")
        ):
            return result
        if "door_presence" not in setup.get("sources", []):
            result["state"] = "presence_source_required"
            return result
        result["state"] = "observing"
        sources = {v["source"]: v for v in context(s, full=True)}
        if (
            preference(s, SYSTEM, KEY, {}) != setup
            or {**DEFAULTS, **preference(s, profile, CONFIG, {})} != cfg
        ):
            return {**result, "state": "context_changed"}
        room = sources.get("room_activity", {})
        devices = sources.get("home_devices", {})
        room_items = room.get("items", []) if room.get("complete") is True else []
        device_items = devices.get("items", []) if devices.get("complete") is True else []
        lights = [
            v
            for v in room_items
            if v.get("category") in ("light", "switch") and v.get("state") == "on"
        ]
        covers = [
            v
            for v in device_items
            if v.get("category") == "cover" and v.get("state") in ("open", "opening")
        ]
        now = s.clock()
        evidence = preference(s, profile, EVIDENCE, {})
        revisions = [
            preference(s, SYSTEM, "feed_revision." + source)
            for source in ("room_activity", "home_devices")
        ]
        setup_row = s.db.execute(
            "SELECT updated_at FROM preferences WHERE subject=? AND key=?", (SYSTEM, KEY)
        ).fetchone()
        policy_row = s.db.execute(
            "SELECT updated_at FROM preferences WHERE subject=? AND key=?", (profile, CONFIG)
        ).fetchone()
        if setup_row is None or policy_row is None:
            return {**result, "state": "context_changed"}
        setup_changed, policy_changed = setup_row[0], policy_row[0]
        scope = hashlib.sha256(
            encode([setup_changed, policy_changed, revisions]).encode()
        ).hexdigest()
        if evidence.get("_scope") != scope:
            evidence = {}
        current = {"_scope": scope}
        samples = {}
        if s.db.execute("SELECT 1 FROM sqlite_master WHERE name='context_records'").fetchone():
            for row in s.db.execute(
                "SELECT source,item_id,last_seen,reports FROM context_records WHERE subject='unknown' AND expires_at>? AND valid_until>?",
                (now, now),
            ):
                samples[row["item_id"]] = (row["last_seen"], row["reports"])

        def held(key, delay, max_gap, sample):
            old = evidence.get(key, {})
            valid = 0 <= now - old.get("last", -1e20) <= max_gap
            first = (
                old.get("first", sample) if valid else max(sample, setup_changed, policy_changed)
            )
            current[key] = {"first": first, "last": sample}
            return 0 <= first <= sample - delay

        candidates = []
        if (
            cfg["departure_enabled"]
            and "door_presence" in setup.get("sources", [])
            and _home(self.home, ("away", "probably_away"))
            and lights
        ):
            if held(
                "away",
                cfg["departure_away_minutes"] * 60,
                150,
                min(
                    [
                        self.home.get("updated_at", now),
                        *[samples.get(v["id"], (now, 0))[0] for v in lights],
                    ]
                ),
            ):
                text = (
                    "The home estimate is away, while "
                    + ", ".join(label(v) for v in lights[:3])
                    + " reports on. Worth checking if those lights are still wanted."
                )
                candidates.append(self._candidate("departure", text, lights, "dashboard_only"))
        local = datetime.fromtimestamp(now, ZoneInfo(setup["timezone"])).strftime("%H:%M")
        start, end = cfg["bedtime_start"], cfg["bedtime_end"]
        bedtime = start <= local < end if start < end else local >= start or local < end
        if (
            cfg["bedtime_enabled"]
            and bedtime
            and _home(self.home, ("home",))
            and (lights or covers)
        ):
            parts = []
            if lights:
                parts.append(", ".join(label(v) for v in lights[:2]) + " reports on")
            if covers:
                parts.append(", ".join(label(v) for v in covers[:2]) + " reports open")
            candidates.append(
                self._candidate(
                    "bedtime",
                    "If you're winding down, " + "; ".join(parts) + ". Would you like to check?",
                    lights[:2] + covers[:2],
                    "proactive",
                )
            )
        if cfg["comfort_enabled"] and _home(self.home, ("home",)):
            for item in device_items:
                if item.get("category") != "climate" or item.get("state") in (
                    "unknown",
                    "unavailable",
                ):
                    continue
                try:
                    temperature = float(item["current_temperature"])
                    unit = item["unit"]
                    if unit in ("°F", "F"):
                        temperature = (temperature - 32) * 5 / 9
                    elif unit not in ("°C", "C"):
                        continue
                    if not math.isfinite(temperature) or not -20 <= temperature <= 60:
                        continue
                except (KeyError, ValueError, TypeError):
                    continue
                direction = (
                    "cool"
                    if temperature < cfg["cold_c"]
                    else "warm"
                    if temperature > cfg["hot_c"]
                    else None
                )
                if (
                    direction
                    and held(
                        "comfort:" + item["id"] + ":" + direction,
                        cfg["comfort_hold_minutes"] * 60,
                        950,
                        samples.get(item["id"], (now, 0))[0],
                    )
                    and samples.get(item["id"], (now, 0))[1] >= 2
                ):
                    text = (
                        label(item)
                        + " reports "
                        + str(round(temperature, 1))
                        + " degrees Celsius, outside your "
                        + direction
                        + " comfort threshold. Would checking the room or adjusting a layer help?"
                    )
                    candidates.append(self._candidate("comfort", text, [item], "proactive"))
        if update and current != evidence:
            owned = not s.db.in_transaction
            if owned:
                s.db.execute("BEGIN IMMEDIATE")
            try:
                if (
                    preference(s, SYSTEM, KEY, {}) == setup
                    and {**DEFAULTS, **preference(s, profile, CONFIG, {})} == cfg
                ):
                    s.db.execute(
                        "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                        (profile, EVIDENCE, encode(current), now),
                    )
                else:
                    result["preview"] = []
                    if owned:
                        s.db.rollback()
                    return result
                if owned:
                    s.db.commit()
            except BaseException:
                if owned:
                    s.db.rollback()
                raise
        deliveries = preference(s, profile, DELIVERY, {})
        for candidate in candidates:
            last = deliveries.get(candidate["topic"], 0)
            if not isinstance(last, (int, float)) or not math.isfinite(last) or last > now:
                continue
            if now - last < cfg["cooldown_hours"] * 3600:
                continue
            result["preview"].append(candidate)
        if (
            preference(s, SYSTEM, KEY, {}) != setup
            or {**DEFAULTS, **preference(s, profile, CONFIG, {})} != cfg
        ):
            result.update(preview=[], state="context_changed")
        return result

    def _candidate(self, topic, text, refs, delivery):
        evidence = [
            {k: v.get(k) for k in ("id", "state", "current_temperature", "unit", "label")}
            for v in refs
        ]
        signature = hashlib.sha256(encode([topic, evidence]).encode()).hexdigest()
        return {"topic": topic, "text": text[:280], "delivery": delivery, "signature": signature}

    def offer(self, *, update=False):
        return next(
            (v for v in self.snapshot(update=update)["preview"] if v["delivery"] == "proactive"),
            None,
        )

    def delivered(self, candidate):
        owned = not self.store.db.in_transaction
        if owned:
            self.store.db.execute("BEGIN IMMEDIATE")
        try:
            setup = preference(self.store, SYSTEM, KEY, {})
            if not setup.get("profile") or candidate not in self.snapshot()["preview"]:
                if owned:
                    self.store.db.rollback()
                return False
            profile = setup["profile"]
            values = preference(self.store, profile, DELIVERY, {})
            values[candidate["topic"]] = self.store.clock()
            self.store.db.execute(
                "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (profile, DELIVERY, encode(values), self.store.clock()),
            )
            if owned:
                self.store.db.commit()
            return True
        except BaseException:
            if owned:
                self.store.db.rollback()
            raise

#!/usr/bin/env python3
"""Replay invented context telemetry through real adapters, without network or actions.

Ground truth is deliberately not an input. Sensor refreshes model an explicit
five-minute polling contract, not new physical transitions or inferred intentions.
"""

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from okabebot.amadeus_habits import HabitPlanner, configure  # noqa: E402
from okabebot.amadeus_onboarding import Onboarding, SOURCES  # noqa: E402
from okabebot.amadeus_sources import Collector  # noqa: E402
from okabebot.morning import Morning  # noqa: E402


def stamp(value):
    if type(value) in (int, float):
        return value
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Timestamps require timezone offsets")
    return date.timestamp()


def deny_network(*args, **kwargs):
    raise RuntimeError("Offline replay cannot access network or devices")


def stream_key(event):
    source, payload = event["source"], event["payload"]
    if source == "availability":
        return source, payload["entity_id"]
    if source == "ha" and payload["entity_id"] in ("person.resident", "media_player.television"):
        return source, payload["entity_id"]
    if source == "media":
        return source, payload["app"]
    if source == "calendar":
        return source, "snapshot"
    return None


def calendar_coverage(events):
    """Flag inconsistent inventories without fabricating cancelled/ongoing facts.

    A removed ongoing busy interval is ambiguous without explicit cancellation
    metadata. Fail closed through its former end rather than resurrect its title.
    Removing a known free interval is a data caveat, not an invented busy period.
    """
    events = sorted(deepcopy(events), key=lambda e: stamp(e["at"]))
    previous, uncertain_until, warnings = [], 0, []
    for event in events:
        if event["source"] != "calendar":
            continue
        payload = event["payload"]
        checked = stamp(payload["calendar_checked_at"])
        current = payload["calendar_upcoming"]
        identities = {(item["title"], stamp(item["start"])) for item in current}
        for item in previous:
            start, end = stamp(item["start"]), stamp(item["end"])
            if start <= checked < end and (item["title"], start) not in identities:
                warnings.append(
                    {
                        "at": event["at"],
                        "kind": "ongoing_calendar_entry_omitted",
                        "busy": item["busy"],
                        "previous_end": end,
                        "policy": "busy_coverage_partial_until_previous_end"
                        if item["busy"]
                        else "nonbusy_inventory_caveat",
                    }
                )
                if item["busy"]:
                    uncertain_until = max(uncertain_until, end)
        event["_calendar_uncertain_until"] = uncertain_until
        previous = current
    return events, warnings


def expand(events, end):
    """Refresh each independently observed stream, retaining explicit outages."""
    events, _ = calendar_coverage(events)
    outages = defaultdict(list)
    for event in events:
        if event["source"].endswith("_outage"):
            outages[event["source"].removesuffix("_outage")].append(
                (stamp(event["at"]), stamp(event["payload"]["until"]))
            )
    expanded = []
    daily_initials = set()
    for index, event in enumerate(events):
        if event["source"].endswith("_outage"):
            continue
        event["_delivery"] = stamp(event["at"]) + event.get("delivery_delay_s", 0)
        event["_refresh"] = False
        if event["source"] == "availability":
            # This fixture contract includes a daily initial state, not an
            # observed transition. Never turn initial charging=off into unplug.
            day = (
                datetime.fromisoformat(event["at"].replace("Z", "+00:00")).date()
                if isinstance(event["at"], str)
                else datetime.fromtimestamp(event["at"], timezone.utc).date()
            )
            initial = (day, event["payload"]["entity_id"])
            if initial not in daily_initials:
                event["payload"]["event_id"] = f"snapshot:initial:{index}"
                daily_initials.add(initial)
        expanded.append(event)
        if event.get("duplicate"):
            expanded.append(dict(event, _delivery=event["_delivery"] + 1))
        key = stream_key(event)
        if key is None:
            continue
        next_at = next(
            (
                stamp(v["at"]) + v.get("delivery_delay_s", 0)
                for v in events[index + 1 :]
                if stream_key(v) == key
            ),
            end + 1,
        )
        # Unknown values stay unknown. Refreshing them does not imply readiness.
        # A media stop is retained as the current app state; it is not completion.
        for at in range(int(event["_delivery"]) + 300, int(min(next_at, end + 1)), 300):
            if any(start <= at < until for start, until in outages[event["source"]]):
                continue
            clone = deepcopy(event)
            clone.update(at=at, _delivery=at, _refresh=True)
            payload = clone["payload"]
            if event["source"] == "calendar":
                payload["calendar_checked_at"] = at
            elif event["source"] == "media":
                payload["updated_at"] = at
            else:
                payload["observed_at"] = at
                payload["event_id"] = f"snapshot:{index}:{at}"
            expanded.append(clone)
    return sorted(expanded, key=lambda event: event["_delivery"])


class Replay:
    def __init__(self, folder, initial, profile, catalog, engine):
        self.folder = Path(folder)
        if self.folder.exists():
            raise ValueError("Use a new isolated output directory")
        self.now, self.profile, self.engine = initial, profile, engine
        self.zone = ZoneInfo(profile["timezone"])
        self.owner = Onboarding(self.folder)
        self.owner.store.clock = lambda: self.now
        topics = profile.get("coaching_topics", [])
        self.owner.save(
            dict(
                profile="synthetic-resident",
                sources=list(SOURCES),
                retention_days=30,
                timezone=profile["timezone"],
                quiet_start=profile["quiet_start"],
                quiet_end=profile["quiet_end"],
                coaching_choice="choose_topics" if topics else "not_now",
                coaching_topics=topics,
                coaching_mode="reaffirm",
            )
        )
        self.owner.control({"paused": False})
        (self.folder / "ha-bindings.json").write_text(
            json.dumps(
                {
                    "door": ["binary_sensor.front_door"],
                    "presence": ["person.resident"],
                    "tv": ["media_player.television"],
                    "interactive": ["binary_sensor.phone_interactive"],
                    "alarm": ["sensor.phone_next_alarm"],
                    "weather": ["weather.home"],
                    "availability": {
                        "dnd": ["binary_sensor.phone_dnd"],
                        "focus": ["binary_sensor.work_focus"],
                        "charging": ["binary_sensor.phone_charging"],
                        "room": ["binary_sensor.room_occupied"],
                    },
                }
            )
        )
        self.collector = Collector(self.folder, clock=lambda: self.now)
        self.morning = Morning(self.folder, clock=lambda: self.now)
        configure(self.owner.store, enabled=True)
        if engine == "baseline":
            self.planner = HabitPlanner(self.owner.store)
        else:
            from okabebot.amadeus_opportunities import ContextPlanner, configure_context

            configure_context(
                self.owner.store, profile="synthetic-resident", preferences=profile, catalog=catalog
            )
            self.planner = ContextPlanner(self.owner.store)
        self.rows, self.seen = [], set()

    def ingest(self, event):
        self.now = event["_delivery"]
        source, payload = event["source"], deepcopy(event["payload"])
        for field in ("observed_at", "updated_at", "calendar_checked_at"):
            if field in payload:
                payload[field] = stamp(payload[field])
        if source == "morning":
            if "updated_at" in payload["details"]:
                payload["details"]["updated_at"] = stamp(payload["details"]["updated_at"])
            return self.morning.observe(payload)
        if source == "ha":
            return self.collector.home_assistant(payload)
        if source == "availability":
            return self.collector.availability(payload)
        if source == "calendar":
            payload["calendar_upcoming"] = [
                dict(value, start=stamp(value["start"]), end=stamp(value["end"]))
                for value in payload["calendar_upcoming"]
            ]
            # The invented input contract explicitly declares full busy/end coverage.
            # A real future-only feed must not set this capability implicitly.
            payload["calendar_busy_complete"] = self.now >= event.get(
                "_calendar_uncertain_until", 0
            )
            return self.collector.calendar(payload)
        if source == "media":
            return self.collector.media(payload)
        if source == "interaction":
            return self.collector.interaction(payload["kind"])
        raise ValueError(f"Unsupported telemetry source: {source}")

    def predict(self):
        snapshot = self.planner.snapshot()
        for proposal in snapshot["proposals"]:
            key = (proposal["proposal_id"], proposal["reason"])
            if key not in self.seen:
                self.rows.append({"at": self.now, "kind": "habit_candidate", "proposal": proposal})
                self.seen.add(key)
            if proposal["eligible"]:
                self.planner.acknowledge(proposal)
                self.rows.append(
                    {
                        "at": self.now,
                        "kind": "habit_suggestion",
                        "proposal": proposal,
                        "delivery": "isolated_shadow_ack",
                        "channel": "quiet_card",
                    }
                )

    def run(self, events, *, predict_after=None):
        start = min(stamp(e["at"]) for e in events)
        last = max(stamp(e["at"]) for e in events)
        last_local = datetime.fromtimestamp(last, self.zone)
        end = (
            last_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        ).timestamp() - 1
        expanded = expand(events, end)
        index = 0
        for tick in range(int(start // 60) * 60, int(end) + 1, 60):
            changed = False
            while index < len(expanded) and expanded[index]["_delivery"] <= tick:
                event = expanded[index]
                index += 1
                try:
                    result = self.ingest(event)
                except (ValueError, PermissionError, OSError, KeyError, TypeError) as exc:
                    result = {"state": "rejected", "error": type(exc).__name__, "detail": str(exc)}
                self.rows.append(
                    {
                        "at": self.now,
                        "kind": "ingestion",
                        "source": event["source"],
                        "refresh": event["_refresh"],
                        "result": result,
                    }
                )
                changed = changed or not event["_refresh"]
            self.now = tick
            # Batch same-time observations before evaluating: initial DND must not
            # arrive after a suggestion merely because the fixture listed it last.
            if (predict_after is None or tick >= predict_after) and (changed or tick % 300 == 0):
                self.predict()
        days = {}
        day = datetime.fromtimestamp(start, self.zone).date()
        while day <= last_local.date():
            days[day.isoformat()] = {"date": day.isoformat(), "suggestions": [], "blocked": {}}
            day += timedelta(days=1)
        reasons = defaultdict(Counter)
        for row in self.rows:
            date = datetime.fromtimestamp(row["at"], self.zone).date().isoformat()
            if row["kind"] == "habit_suggestion":
                days[date]["suggestions"].append(
                    dict(row, local_at=datetime.fromtimestamp(row["at"], self.zone).isoformat())
                )
            elif row["kind"] == "habit_candidate" and not row["proposal"]["eligible"]:
                reasons[date][row["proposal"]["reason"]] += 1
        for date, value in days.items():
            value["blocked"] = dict(reasons[date])
        return {"engine": self.engine, "days": list(days.values()), "rows": self.rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("events", "profile", "catalog", "output"):
        parser.add_argument(f"--{argument}", type=Path, required=True)
    parser.add_argument(
        "--warmup", type=Path, help="Earlier invented telemetry; never ground truth"
    )
    parser.add_argument(
        "--warmup-mode",
        choices=("replay", "observe-only"),
        default="replay",
        help="Observe-only ingests historical telemetry without historical proposals or deliveries",
    )
    parser.add_argument("--engine", choices=("baseline", "context"), required=True)
    args = parser.parse_args()
    events = json.loads(args.events.read_text())
    if not isinstance(events, list) or not events:
        raise ValueError("Provide a nonempty invented telemetry array")
    evaluation_start = min(stamp(e["at"]) for e in events)
    if args.warmup:
        warmup = json.loads(args.warmup.read_text())
        if not isinstance(warmup, list) or any(stamp(e["at"]) >= evaluation_start for e in warmup):
            raise ValueError("Warmup telemetry must precede the evaluation input")
        events = warmup + events
    profile, catalog = json.loads(args.profile.read_text()), json.loads(args.catalog.read_text())
    manifest = {
        field: hashlib.sha256(getattr(args, field).read_bytes()).hexdigest()
        for field in ("events", "profile", "catalog")
    }
    socket.socket = deny_network
    socket.create_connection = deny_network
    replay = Replay(args.output, min(stamp(e["at"]) for e in events), profile, catalog, args.engine)
    try:
        result = replay.run(
            events,
            predict_after=evaluation_start if args.warmup_mode == "observe-only" else None,
        )
        _, result["input_validation"] = calendar_coverage(events)
        evaluation_date = datetime.fromtimestamp(evaluation_start, replay.zone).date().isoformat()
        for day in result["days"]:
            day["evaluation"] = day["date"] >= evaluation_date
        result["evaluation_start"] = evaluation_start
        result["warmup_mode"] = args.warmup_mode if args.warmup else "none"
        if args.warmup:
            manifest["warmup"] = hashlib.sha256(args.warmup.read_bytes()).hexdigest()
        result["input_hashes"] = manifest
        (args.output / "outputs.json").write_text(json.dumps(result, indent=2))
        print(
            json.dumps(
                {
                    "engine": args.engine,
                    "days": len(result["days"]),
                    "suggestions": sum(len(d["suggestions"]) for d in result["days"]),
                }
            )
        )
    finally:
        replay.owner.close()


if __name__ == "__main__":
    main()

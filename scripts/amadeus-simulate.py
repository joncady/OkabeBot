#!/usr/bin/env python3
"""Offline accelerated replay. Input telemetry only; no ground truth, network or hardware."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from okabebot.amadeus_onboarding import Onboarding, SOURCES  # noqa: E402
from okabebot.amadeus_coaching import Coaching  # noqa: E402
from okabebot.amadeus_sources import Collector  # noqa: E402
from okabebot.morning import Morning, DEFAULTS  # noqa: E402
from okabebot.morning_briefing import Briefing  # noqa: E402
from okabebot.amadeus_habits import HabitPlanner, configure, feedback  # noqa: E402


def stamp(value):
    if type(value) in (int, float):
        return value
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Timestamps require timezone offsets")
    return date.timestamp()


def deny_network(*args, **kwargs):
    raise RuntimeError("Simulation cannot open network or device sockets")


class Replay:
    def __init__(self, folder, initial, *, quiet_start="22:00", quiet_end="07:00", habits=False):
        self.folder = Path(folder)
        if self.folder.exists():
            raise ValueError("Use a new isolated output directory")
        self.now = initial
        self.owner = Onboarding(self.folder)
        self.owner.store.clock = lambda: self.now
        self.owner.save(
            dict(
                profile="synthetic-resident",
                sources=list(SOURCES),
                retention_days=30,
                timezone="America/Los_Angeles",
                quiet_start=quiet_start,
                quiet_end=quiet_end,
                coaching_choice="choose_topics",
                coaching_topics=["hydration", "movement", "rest", "meals"],
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
                }
            )
        )
        self.collector = Collector(self.folder, clock=lambda: self.now)
        self.morning = Morning(self.folder, clock=lambda: self.now)
        self.morning.configure(
            dict(DEFAULTS, enabled=True, destination="sim-tv", present_on_wake=True),
            [{"id": "sim-tv", "adapter": "cast"}],
        )
        self.briefing = Briefing(self.folder, clock=lambda: self.now)
        self.briefing.configure(
            dict(enabled=True, name="Resident", coaching=True, quiet_override=False)
        )
        self.rows = []
        self.habits = habits
        if habits:
            configure(self.owner.store, enabled=True)
        self.planner = HabitPlanner(self.owner.store)
        self.last_candidates = {}

    def predict(self):
        if not self.habits:
            return
        result = self.planner.snapshot()
        for p in result["proposals"]:
            key = (p["proposal_id"], p["reason"])
            if key not in self.last_candidates:
                self.rows.append({"at": self.now, "kind": "habit_candidate", "proposal": p})
                self.last_candidates[key] = True
            if p["eligible"]:
                self.planner.acknowledge(p)
                self.rows.append(
                    {
                        "at": self.now,
                        "kind": "habit_suggestion",
                        "proposal": p,
                        "delivery": "simulated_ack",
                    }
                )

    def deliver(self):
        summary = self.briefing.enrich(self.morning.view("sim-tv"))
        if not summary:
            return
        self.rows.append(
            {
                "at": self.now,
                "kind": "morning_cards",
                "expires_at": self.now + self.morning.settings()["display_minutes"] * 60,
                "cards": summary["cards"],
                "delivery": "simulated_ready_tv",
            }
        )
        if not self.briefing.claim("sim-tv"):
            self.rows.append(
                {"at": self.now, "kind": "speech_suppressed", "reason": "production_claim_gate"}
            )
            return
        # Deliberately no model/speech import: exact production facts/gates, deterministic wording.
        message, generated, coach = self.briefing.message(summary, {"persona": "synthetic"})
        self.rows.append(
            {
                "at": self.now,
                "kind": "morning_briefing",
                "cards": summary["cards"],
                "text": message,
                "generated_framing": generated,
                "coaching_topic": coach["topic"] if coach else None,
                "delivery": "simulated_ack",
            }
        )
        self.briefing.complete(success=True, coach=coach)

    def event(self, event):
        self.now = event["_delivery"]
        source, p = event["source"], dict(event["payload"])
        for key in ("observed_at", "updated_at", "calendar_checked_at"):
            if key in p:
                p[key] = stamp(p[key])
        if source in ("ha", "morning"):
            if source == "morning" and "updated_at" in p["details"]:
                p["details"] = dict(p["details"], updated_at=stamp(p["details"]["updated_at"]))
            result = self.collector.home_assistant(p) if source == "ha" else self.morning.observe(p)
        elif source == "calendar":
            p["calendar_upcoming"] = [
                dict(v, start=stamp(v["start"])) for v in p["calendar_upcoming"]
            ]
            result = self.collector.calendar(p)
        elif source == "media":
            result = self.collector.media(p)
        elif source == "interaction":
            result = self.collector.interaction(p["kind"])
        elif source == "feedback":
            scope = p.get("scope", "routine" if p.get("kind") else "coaching")
            response = stamp(p["response_at"]) if p.get("response_at") else None
            expected = {
                "routine": "habit_suggestion",
                "morning_audio": "morning_briefing",
                "morning_cards": "morning_cards",
                "coaching": "morning_briefing",
            }[scope]
            matches = [
                r
                for r in self.rows
                if r["kind"] == expected and (response is None or abs(r["at"] - response) < 2)
            ]
            if scope == "routine":
                matches = [r for r in matches if r["proposal"]["kind"] == p["kind"]]
            if not matches:
                return {"state": "feedback_no_matching_delivery", "scope": scope}

            if scope == "routine":
                feedback(
                    self.owner.store,
                    "synthetic-resident",
                    p["kind"],
                    p["outcome"],
                    delay_minutes=p.get("requested_delay_minutes", 1440),
                )
                result = {"state": "feedback_applied", "scope": scope}
            elif scope == "morning_audio" and p["outcome"] == "stop":
                voice = {
                    k: self.briefing.settings()[k]
                    for k in ("enabled", "name", "coaching", "quiet_override")
                }
                self.briefing.configure(dict(voice, enabled=False))
                result = {"state": "feedback_applied", "scope": scope}
            elif scope == "coaching":
                outcome = "topic_off" if p["outcome"] == "stop" and p.get("topic") else p["outcome"]
                value = Coaching(self.owner.store, timezone="America/Los_Angeles").feedback(
                    "synthetic-resident", outcome, topic=p.get("topic")
                )
                result = {"state": "feedback_applied", "scope": scope, "enabled": value["enabled"]}
            else:
                result = {"state": "feedback_unsupported", "scope": scope, "outcome": p["outcome"]}
        else:
            raise ValueError("Unsupported input source")
        return result

    def run(self, events, *, end=None):
        # Refresh only successful calendar/media snapshots, never fabricate missing physical sensors.
        expanded = []
        for i, e in enumerate(events):
            e = dict(e)
            e["_delivery"] = stamp(e["at"]) + e.get("delivery_delay_s", 0)
            if e["source"] == "calendar_outage":
                continue
            expanded.append(e)
            if e.get("duplicate"):
                expanded.append(dict(e, _delivery=e["_delivery"] + 1))
            if e["source"] not in ("calendar", "media"):
                continue
            next_at = next(
                (stamp(v["at"]) for v in events[i + 1 :] if v["source"] == e["source"]),
                None,
            )
            until = min(next_at or e["_delivery"] + 86400, e["_delivery"] + 86400)
            if e["source"] == "media" and e["payload"]["state"] not in (
                "PLAYING",
                "PAUSED",
                "BUFFERING",
            ):
                continue
            for at in range(int(e["_delivery"]) + 300, int(until), 300):
                if e["source"] == "calendar" and any(
                    v["source"] == "calendar_outage"
                    and stamp(v["at"]) <= at < stamp(v["payload"]["until"])
                    for v in events
                ):
                    continue
                clone = dict(e, at=at, _delivery=at, payload=dict(e["payload"]))
                field = "calendar_checked_at" if e["source"] == "calendar" else "updated_at"
                clone["payload"][field] = at
                expanded.append(clone)
        expanded.sort(key=lambda e: e["_delivery"])
        # One-minute policy ticks plus event timestamps preserve temporal order and freshness.
        ticks = range(
            int(expanded[0]["_delivery"] // 60) * 60,
            int(end or max(stamp(e["at"]) + e.get("delivery_delay_s", 0) for e in events) + 3600)
            + 1,
            60,
        )
        index = 0
        for tick in ticks:
            while index < len(expanded) and expanded[index]["_delivery"] <= tick:
                e = expanded[index]
                index += 1
                try:
                    result = self.event(e)
                except (ValueError, PermissionError, OSError, KeyError, TypeError) as exc:
                    result = {"state": "rejected", "error": type(exc).__name__, "detail": str(exc)}
                self.rows.append(
                    {"at": self.now, "kind": "ingestion", "source": e["source"], "result": result}
                )
                # Live HTTP dispatch only runs when observe reports a newly prepared day.
                if result.get("prepared"):
                    self.deliver()
                if e["source"] not in ("calendar", "media"):
                    self.predict()
            self.now = tick
            if tick % 300 == 0:
                self.predict()
            if tick % 1800 == 0:
                summary = self.morning.view("sim-tv")
                self.rows.append(
                    {
                        "at": tick,
                        "kind": "checkpoint",
                        "morning_visible": bool(summary),
                        "cards": summary["cards"] if summary else [],
                        "general_predictions": [],
                    }
                )
        return self.rows

    def close(self):
        self.owner.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--habits",
        action="store_true",
        help="Enable initial shadow learner only inside this replay",
    )
    args = parser.parse_args()
    events = json.loads(args.events.read_text())
    if not isinstance(events, list) or not events:
        raise ValueError("Provide a nonempty telemetry array")
    events.sort(key=lambda e: stamp(e["at"]))
    # No imports of live config/controller/voice/surfaces; fail closed on accidental networking.
    socket.socket = deny_network
    socket.create_connection = deny_network
    replay = Replay(args.output, stamp(events[0]["at"]), habits=args.habits)
    try:
        rows = replay.run(events)
        (args.output / "outputs.json").write_text(json.dumps(rows, indent=2))
        print(
            json.dumps(
                {
                    "events": len(events),
                    "records": len(rows),
                    "briefings": sum(r["kind"] == "morning_briefing" for r in rows),
                }
            )
        )
    finally:
        replay.close()


if __name__ == "__main__":
    main()

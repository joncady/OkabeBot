#!/usr/bin/env python3
"""Post-replay evaluator. Ground truth is read here, never by the telemetry runner."""

import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def timestamp(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def evaluate(truth, outputs, *, after=None):
    days = truth["days"]
    if after:
        days = [d for d in days if d["date"] >= after]
    zone = ZoneInfo("America/Los_Angeles")
    lookup = {d["date"]: d for d in days}
    mapping = {"wake": "daily_overview", "departure": "departure_help", "media": "evening_choice"}
    notifications = []
    windows = set()
    available_windows = set()
    timing = []
    invalid = []
    for day in days:
        if (
            day.get("actual_leave")
            and day.get("actual_return")
            and timestamp(day["actual_return"]) < timestamp(day["actual_leave"])
        ):
            invalid.append({"date": day["date"], "reason": "return_precedes_departure"})
        for section in ("activities", "help_windows", "do_not_interrupt"):
            for item in day[section]:
                if timestamp(item["end"]) <= timestamp(item["start"]):
                    invalid.append(
                        {"date": day["date"], "reason": "nonpositive_interval", "section": section}
                    )
    seen = set()
    for row in outputs:
        at = row["at"]
        date = datetime.fromtimestamp(at, zone).date().isoformat()
        day = lookup.get(date)
        if not day:
            continue
        if row["kind"] == "habit_candidate":
            p = row["proposal"]
            key = (date, p["kind"])
            if key not in seen:
                seen.add(key)
                target = None
                if p["kind"] == "wake":
                    target = day.get("actual_wake")
                elif p["kind"] == "departure":
                    target = day.get("actual_leave")
                else:
                    person = truth["persona"]["name"].casefold()
                    choices = [
                        a["start"]
                        for a in day["activities"]
                        if person in a["who"].casefold()
                        and any(
                            w in a["activity"].casefold() for w in ("watch", "television", "movie")
                        )
                    ]
                    target = min(choices) if choices else None
                delta = None
                if target:
                    actual = datetime.fromisoformat(target)
                    delta = abs(actual.hour * 60 + actual.minute - p["routine"]["minute"])
                timing.append(
                    {
                        "date": date,
                        "kind": p["kind"],
                        "absolute_error_minutes": delta,
                        "activity_occurred": bool(target),
                        "within_window": delta is not None
                        and delta <= p["routine"]["window_minutes"] / 2,
                        "support": p["routine"]["support"],
                        "scope": p["routine"].get("scope", "unknown"),
                    }
                )
        if row["kind"] not in ("morning_cards", "morning_briefing", "habit_suggestion"):
            continue
        p = row.get("proposal", {})
        kind = mapping.get(p.get("kind"), "daily_overview")
        matching = []
        for index, w in enumerate(day["help_windows"]):
            if w["kind"] == kind and timestamp(w["start"]) <= at <= timestamp(w["end"]):
                matching.append(index)
                windows.add((date, index))
        # Separate arrival timing from persistent-card availability. The replay
        # fixture keeps its TV ready for the configured two-hour morning run.
        until = (
            row.get("expires_at", at + 120 * 60)
            if row["kind"] == "morning_cards"
            else row.get("proposal", {}).get("expires_at", at)
        )
        for index, w in enumerate(day["help_windows"]):
            if w["kind"] == kind and max(at, timestamp(w["start"])) <= min(
                until, timestamp(w["end"])
            ):
                available_windows.add((date, index))
        blocked = [
            w["reason"]
            for w in day["do_not_interrupt"]
            if timestamp(w["start"]) <= at <= timestamp(w["end"])
        ]
        notifications.append(
            {
                "at": at,
                "date": date,
                "kind": kind,
                "origin": row["kind"],
                "in_help_window": bool(matching),
                "unwelcome_overlap": bool(blocked),
                "reasons": blocked,
            }
        )
    supported = sum(w["kind"] in set(mapping.values()) for d in days for w in d["help_windows"])
    return {
        "days": len(days),
        "notifications": len(notifications),
        "in_help_window": sum(n["in_help_window"] for n in notifications),
        "unwelcome_overlap": sum(n["unwelcome_overlap"] for n in notifications),
        "covered_supported_windows": len(windows),
        "available_during_supported_windows": len(available_windows),
        "supported_windows": supported,
        "routine_predictions": len(timing),
        "routine_within_window": sum(t["within_window"] for t in timing),
        "timing_details": timing,
        "notification_details": notifications,
        "truth_errors": invalid,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--truth", type=Path, required=True)
    p.add_argument("--outputs", type=Path, required=True)
    p.add_argument("--after")
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    result = evaluate(
        json.loads(args.truth.read_text()), json.loads(args.outputs.read_text()), after=args.after
    )
    args.report.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if not isinstance(v, list)}))


if __name__ == "__main__":
    main()

"""Private bounded planner evaluations. No dispatcher, model calls or device access."""

from contextlib import closing
import json
from pathlib import Path
import time
from .amadeus import Store, encode
from .amadeus_habits import HabitPlanner, DEFAULTS, CONFIG_KEY, preference
from .amadeus_opportunities import ContextPlanner
from .amadeus_onboarding import SYSTEM, KEY

CONFIG = "shadow.config"


def table(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS shadow_decisions (id INTEGER PRIMARY KEY, subject TEXT NOT NULL, evaluated_at REAL NOT NULL, payload TEXT NOT NULL)"
    )


class ShadowTrial:
    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = Path(folder), clock
        self.state = {"enabled": False, "status": "disabled", "delivery_enabled": False}

    def store(self):
        return closing(Store(self.folder, clock=self.clock))

    def configure(self, data):
        if set(data) != {"enabled"} or type(data["enabled"]) is not bool:
            raise ValueError("Choose shadow trial on or off")
        with self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            if not setup.get("profile") or setup.get("paused") or setup.get("guest"):
                raise ValueError("Active private setup required")
            profile = setup["profile"]
            prefs = preference(s, profile, "context.preferences", {})
            goals = prefs.setdefault("goals", [])
            if not isinstance(goals, list) or any(not isinstance(g, dict) for g in goals):
                raise ValueError("Review context goals in private setup")
            if data["enabled"]:
                existing = {g.get("kind") for g in goals}
                goals.extend(
                    {"kind": kind, "enabled": True}
                    for kind in ("morning", "departure", "media")
                    if kind not in existing
                )
            values = [
                (SYSTEM, CONFIG, data),
                (
                    SYSTEM,
                    CONFIG_KEY,
                    {
                        **DEFAULTS,
                        **preference(s, SYSTEM, CONFIG_KEY, {}),
                        "enabled": data["enabled"],
                    },
                ),
                (profile, "context.enabled", data["enabled"]),
                (profile, "context.preferences", prefs),
            ]
            rows = [(subject, key, encode(value), self.clock()) for subject, key, value in values]
            with s.db:
                table(s.db)
                s.db.execute(
                    "CREATE TABLE IF NOT EXISTS context_exposures (subject TEXT NOT NULL, identity TEXT NOT NULL, shown_at REAL NOT NULL, PRIMARY KEY(subject,identity))"
                )
                s.db.executemany(
                    "INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(subject,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    rows,
                )
        self.state.update(
            enabled=data["enabled"],
            status="waiting for evaluation" if data["enabled"] else "disabled",
        )
        return dict(self.state)

    def tick(self):
        with self.store() as s:
            setup = preference(s, SYSTEM, KEY, {})
            enabled = preference(s, SYSTEM, CONFIG, {}).get("enabled") is True
            self.state["enabled"] = enabled
            if not enabled or not setup.get("profile") or setup.get("paused") or setup.get("guest"):
                self.state["status"] = "paused" if enabled else "disabled"
                return None
            profile = setup["profile"]
            context_prefs = preference(s, profile, "context.preferences", {})
            now = self.clock()
            habit = HabitPlanner(s).snapshot()
            context = ContextPlanner(s).snapshot()
            observed = [
                dict(r)
                for r in s.db.execute(
                    "SELECT source,kind,MAX(observed_at) last_seen FROM events WHERE observed_at<=? AND subject IN (?,?,?) GROUP BY source,kind",
                    (now, profile, "unknown", "household"),
                )
                if r["source"] in setup["sources"]
            ]
            gaps = []
            if not habit["routines"]:
                gaps.append("no_supported_habit_yet")
            if "availability" not in setup["sources"]:
                gaps.append("availability_not_consented")
            if not preference(s, profile, "context.catalog", []):
                gaps.append("verified_media_catalog_missing")
            if not any(
                r["kind"] == "calendar_snapshot" and now - r["last_seen"] <= 600 for r in observed
            ):
                gaps.append("calendar_snapshot_stale_or_missing")
            candidates = []
            for planner in (habit, context):
                for p in planner["proposals"][:6]:
                    candidates.append(
                        {k: p[k] for k in ("proposal_id", "kind", "text", "eligible", "reason")}
                    )
            from .amadeus_feeds import context as feed_context

            result = {
                "source_context": feed_context(s),
                "mode": "shadow",
                "delivery_enabled": False,
                "evaluated_at": now,
                "habit_state": habit["state"],
                "context_state": context["state"],
                "routines": [
                    {k: r[k] for k in ("kind", "matching_days", "observed_days", "support")}
                    for r in habit["routines"]
                ],
                "candidates": candidates,
                "diagnostic_gaps": gaps,
                "input_recency": observed,
                "outcome": "would_offer"
                if any(p["eligible"] for p in candidates)
                else "withheld"
                if candidates
                else "no_candidate",
            }
            while len(json.dumps(result.get("source_context", [])).encode()) > 7000:
                result["source_context"].pop()
            # Bounded private record; no transcript, raw events or model ratings.
            while len(json.dumps(result).encode()) > 12000 and result["candidates"]:
                result["candidates"].pop()
            with s.db:
                s.db.execute("BEGIN IMMEDIATE")
                if (
                    preference(s, SYSTEM, KEY, {}) != setup
                    or preference(s, SYSTEM, CONFIG, {}).get("enabled") is not True
                    or preference(s, profile, "context.preferences", {}) != context_prefs
                ):
                    self.state["status"] = "context changed; evaluation discarded"
                    return None
                table(s.db)
                s.db.execute(
                    "INSERT INTO shadow_decisions(subject,evaluated_at,payload) VALUES (?,?,?)",
                    (profile, now, json.dumps(result)),
                )
                s.db.execute(
                    "DELETE FROM shadow_decisions WHERE evaluated_at<?",
                    (now - min(7, setup["retention_days"]) * 86400,),
                )
                s.db.execute(
                    "DELETE FROM shadow_decisions WHERE id NOT IN (SELECT id FROM shadow_decisions ORDER BY evaluated_at DESC,id DESC LIMIT 2500)"
                )
            self.state.update(
                status=result["outcome"],
                last_evaluated_at=now,
                candidates=len(candidates),
                diagnostic_gaps=gaps,
            )
            return result

    def run(self, stop):
        while not stop.is_set():
            try:
                self.tick()
            except Exception:
                self.state["status"] = "evaluation unavailable"
            stop.wait(300)

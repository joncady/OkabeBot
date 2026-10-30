"""Local shadow routine learning and proposals. Never dispatches notifications or actions."""

from collections import defaultdict
from datetime import datetime
import json
from zoneinfo import ZoneInfo

from .amadeus_onboarding import SYSTEM, KEY

VERSION = "windows-v1"
CONFIG_KEY = "habits.config"
FEEDBACK_KEY = "habits.feedback"
DEFAULTS = {
    "enabled": False,
    "min_days": 4,
    "min_support": 0.6,
    "window_minutes": 45,
    "lead_minutes": 15,
    "max_daily": 2,
}
KINDS = {
    "wake": "Prepare a morning overview?",
    "departure": "Heading out soon? Want a quick check of today?",
    "media": "Want help choosing something to watch?",
}
SOURCES = {"wake": "phone_context", "departure": "door_presence", "media": "media"}


def configure(store, **overrides):
    value = dict(DEFAULTS, **preference(store, SYSTEM, CONFIG_KEY, {}))
    value.update(overrides)
    if set(value) != set(DEFAULTS) or type(value["enabled"]) is not bool:
        raise ValueError("Use supported habit configuration")
    for key, lo, hi in [
        ("min_days", 3, 30),
        ("window_minutes", 15, 120),
        ("lead_minutes", 0, 60),
        ("max_daily", 1, 5),
    ]:
        if type(value[key]) is not int or not lo <= value[key] <= hi:
            raise ValueError("Habit interval outside supported range")
    if type(value["min_support"]) not in (int, float) or not 0.5 <= value["min_support"] <= 1:
        raise ValueError("Require majority evidence")
    store.remember(SYSTEM, CONFIG_KEY, value)
    return value


def preference(store, subject, key, default=None):
    row = store.db.execute(
        "SELECT value FROM preferences WHERE subject=? AND key=?", (subject, key)
    ).fetchone()
    return json.loads(row[0]) if row else default


def feedback(store, profile, kind, outcome, *, delay_minutes=1440):
    if kind not in KINDS or outcome not in ("helpful", "later", "wrong", "stop", "resume"):
        raise ValueError("Use explicit routine feedback")
    if type(delay_minutes) is not int or not 1 <= delay_minutes <= 10080:
        raise ValueError("Choose an explicit delay of one minute to seven days")
    values = preference(store, profile, FEEDBACK_KEY, {})
    value = dict(values.get(kind, {}), outcome=outcome, at=store.clock())
    if outcome == "stop":
        value["disabled"] = True
    if outcome == "wrong":
        value["needs_confirmation"] = True
    if outcome == "resume":
        value["disabled"] = False
        value["needs_confirmation"] = False
    if outcome in ("later", "wrong"):
        value["paused_until"] = store.clock() + delay_minutes * 60
    if outcome == "resume":
        value["paused_until"] = 0
    values[kind] = value
    store.remember(profile, FEEDBACK_KEY, values)


class HabitPlanner:
    def __init__(self, store):
        self.store = store

    def snapshot(self):
        now = self.store.clock()
        setup = preference(self.store, SYSTEM, KEY)
        config = preference(self.store, SYSTEM, CONFIG_KEY, DEFAULTS)
        if (
            not setup
            or not config["enabled"]
            or setup.get("paused") is not False
            or setup.get("guest") is not False
        ):
            return {"version": VERSION, "state": "disabled", "routines": [], "proposals": []}
        profile = setup["profile"]
        zone = ZoneInfo(setup["timezone"])
        today = datetime.fromtimestamp(now, zone).date()
        rows = self.store.db.execute(
            "SELECT id,source,subject,kind,observed_at,payload FROM events WHERE expires_at>? AND observed_at<=? AND subject IN (?,?) ORDER BY observed_at,id",
            (now, now, profile, "unknown"),
        ).fetchall()
        events = [
            dict(r, payload=json.loads(r["payload"]))
            for r in rows
            if r["source"] in setup["sources"]
        ]
        evidence = defaultdict(lambda: defaultdict(list))
        eligible = defaultdict(set)
        previous_presence = None
        previous_media = {}
        for event in events:
            d = datetime.fromtimestamp(event["observed_at"], zone)
            if d.date() >= today:
                continue  # Never fit the day being evaluated.
            bucket = "weekend" if d.weekday() >= 5 else "weekday"
            source = event["source"]
            p = event["payload"]
            for kind, required in SOURCES.items():
                if source == required:
                    eligible[(kind, bucket)].add(d.date().isoformat())
            kind = None
            if event["kind"] == "phone_wake" and p["state"] == "on" and 4 <= d.hour < 12:
                kind = "wake"
            elif event["kind"] == "presence":
                if p["state"] == "away" and previous_presence == "home":
                    kind = "departure"
                previous_presence = p["state"]
            elif event["kind"] == "media":
                # Checkpoints do not create repeated starts; absence of a STOP is not completion.
                app = p.get("app", "")
                old = previous_media.get(app)
                if (
                    p.get("state") == "PLAYING"
                    and old not in ("PLAYING", "BUFFERING")
                    and 16 <= d.hour < 24
                ):
                    kind = "media"
                previous_media[app] = p.get("state")
            if kind:
                evidence[(kind, bucket)][d.date().isoformat()].append(
                    (d.hour * 60 + d.minute, event["id"])
                )
        routines = []
        proposals = []
        bucket = "weekend" if today.weekday() >= 5 else "weekday"
        for kind in KINDS:
            days = evidence[(kind, bucket)]
            observed = eligible[(kind, bucket)]
            if len(observed) < config["min_days"]:
                continue
            # One first cue per observed day. Dense polling never increases the denominator.
            samples = [min(v) for v in days.values()]
            if not samples:
                continue
            width = config["window_minutes"]
            best = max(
                samples, key=lambda center: sum(abs(v[0] - center[0]) <= width / 2 for v in samples)
            )
            members = [v for v in samples if abs(v[0] - best[0]) <= width / 2]
            support = len(members) / len(observed)
            if len(members) < config["min_days"] or support < config["min_support"]:
                continue
            minute = sorted(v[0] for v in members)[len(members) // 2]
            routine = {
                "kind": kind,
                "minute": minute,
                "window_minutes": width,
                "support": round(support, 3),
                "matching_days": len(members),
                "observed_days": len(observed),
                "day_type": bucket,
                "evidence_ids": [v[1] for v in members],
                "version": VERSION,
                "scope": "profile" if kind == "wake" else "household",
            }
            routines.append(routine)
            local = datetime.fromtimestamp(now, zone)
            current = local.hour * 60 + local.minute
            if minute - config["lead_minutes"] <= current < minute + width / 2:
                correction = preference(self.store, profile, FEEDBACK_KEY, {}).get(kind, {})
                revision = correction.get("at", 0) if correction.get("outcome") == "later" else 0
                proposal = dict(
                    kind=kind,
                    text=KINDS[kind],
                    routine=routine,
                    expires_at=now + 15 * 60,
                    action="quiet_card",
                    shadow=True,
                    context=self._context(events),
                    proposal_id=f"{VERSION}:{today.isoformat()}:{kind}:{revision}",
                )
                reason = self._gate(setup, config, events, kind, local)
                proposal.update(eligible=reason is None, reason=reason or "eligible")
                proposals.append(proposal)
        return {"version": VERSION, "state": "shadow", "routines": routines, "proposals": proposals}

    def _context(self, events):
        """Bounded facts only; missing feed coverage never becomes a free-day claim."""
        now = self.store.clock()
        result = {}
        weather = next((e for e in reversed(events) if e["kind"] == "weather"), None)
        if weather and 0 <= now - weather["payload"]["reported_at"] <= 3 * 3600:
            value = weather["payload"]
            result["weather"] = {k: value[k] for k in ("condition", "temperature_c", "reported_at")}
            result["outdoor_gear"] = (["jacket"] if value["temperature_c"] <= 15 else []) + (
                ["umbrella"]
                if value["condition"] in ("rainy", "pouring", "lightning-rainy")
                else []
            )
        marker = next((e for e in reversed(events) if e["kind"] == "calendar_snapshot"), None)
        if marker and 0 <= now - marker["observed_at"] <= 600:
            upcoming = sorted(
                (
                    e["payload"]
                    for e in events
                    if e["kind"] == "calendar"
                    and e["payload"].get("snapshot_id") == marker["payload"]["snapshot_id"]
                    and now < e["payload"]["start_at"] <= now + 4 * 3600
                ),
                key=lambda e: e["start_at"],
            )
            result["upcoming"] = [{k: p[k] for k in ("summary", "start_at")} for p in upcoming[:2]]
            result["calendar_checked_at"] = marker["observed_at"]
        return result

    def _gate(self, setup, config, events, kind, local):
        now = self.store.clock()
        profile = setup["profile"]
        clock = local.strftime("%H:%M")
        start, end = setup["quiet_start"], setup["quiet_end"]
        if start <= clock < end if start < end else clock >= start or clock < end:
            return "quiet"
        f = preference(self.store, profile, FEEDBACK_KEY, {}).get(kind, {})
        if f.get("disabled"):
            return "stopped"
        if f.get("needs_confirmation"):
            return "needs_confirmation"
        if f.get("paused_until", 0) > now:
            return "snoozed"
        recent = preference(self.store, profile, "habits.delivery", [])
        day = local.date().isoformat()
        same = [r for r in recent if r["day"] == day and r["kind"] == kind]
        if same and not (f.get("outcome") == "later" and f.get("at", 0) > same[-1]["at"]):
            return "already_delivered"
        if sum(r["day"] == day for r in recent) >= config["max_daily"]:
            return "daily_limit"
        rescheduled = same and f.get("outcome") == "later" and f.get("at", 0) > same[-1]["at"]
        if recent and now - recent[-1]["at"] < 3600 and not rescheduled:
            return "cooldown"
        presence = next((e for e in reversed(events) if e["kind"] == "presence"), None)
        if (
            not presence
            or now - presence["observed_at"] > 4 * 3600
            or presence["payload"]["state"] != "home"
        ):
            return "home_not_confirmed"
        media = next((e for e in reversed(events) if e["kind"] == "media"), None)
        if (
            media
            and now - media["observed_at"] <= 600
            and media["payload"].get("state") in ("PLAYING", "BUFFERING")
        ):
            return "media_active"
        if kind == "wake":
            screen = next((e for e in reversed(events) if e["kind"] == "phone_wake"), None)
            if (
                not screen
                or screen["payload"]["state"] != "on"
                or now - screen["observed_at"] > 300
            ):
                return "availability_unknown"
        marker = next((e for e in reversed(events) if e["kind"] == "calendar_snapshot"), None)
        if "calendar" in setup["sources"] and (not marker or now - marker["observed_at"] > 600):
            return "calendar_stale"
        if marker:
            sid = marker["payload"]["snapshot_id"]
            if any(
                e["kind"] == "calendar"
                and e["payload"].get("snapshot_id") == sid
                and abs(e["payload"]["start_at"] - now) < 30 * 60
                for e in events
            ):
                return "calendar_nearby"
        return None

    def acknowledge(self, proposal):
        expiry = proposal.get("expires_at")
        if (
            type(expiry) not in (int, float)
            or not self.store.clock() < expiry <= self.store.clock() + 900
        ):
            raise ValueError("Proposal expired or has an invalid lease")
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            self._acknowledge(proposal)

    def _acknowledge(self, proposal):
        # Revalidate current policy and capability rather than trusting a caller-made payload.
        matches = [
            p
            for p in self.snapshot()["proposals"]
            if p["proposal_id"] == proposal["proposal_id"] and p["eligible"]
        ]
        if not matches:
            raise ValueError("Proposal is no longer eligible")
        setup = preference(self.store, SYSTEM, KEY)
        profile = setup["profile"]
        rows = preference(self.store, profile, "habits.delivery", [])
        day = (
            datetime.fromtimestamp(self.store.clock(), ZoneInfo(setup["timezone"]))
            .date()
            .isoformat()
        )
        rows = [r for r in rows if self.store.clock() - r["at"] < 7 * 86400]
        rows.append({"day": day, "kind": matches[0]["kind"], "at": self.store.clock()})
        self.store.remember(profile, "habits.delivery", rows)

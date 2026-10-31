"""Bounded tool-result context and conservative checks for conversational replies."""

from .prompts import prompt

import json
from datetime import datetime
from zoneinfo import ZoneInfo
import re


SYSTEM = prompt("tool-reply")


def calendar_reference(result):
    """Useful spoken fallback without turning one calendar into a complete agenda."""
    if not result.get("available"):
        return "I couldn't read a fresh calendar, so I can't confirm your events."
    events = result.get("events", [])
    if not events:
        reply = "I don't see any events in the calendar I can access for those dates."
    else:
        entries = [
            str(e.get("title", "Untitled event"))[:70]
            + " at "
            + str(e.get("start", "time unavailable"))[:35]
            for e in events[:3]
        ]
        reply = "In the connected calendar: " + "; ".join(entries) + "."
        if len(events) > 3:
            reply += " There are more events in this view."
    if not result.get("start_date"):
        reply += (
            " This view only includes upcoming timed events, not all-day or already-started events."
        )
    return reply


def facts(name, result, reference):
    """Reference always available; only useful explicitly selected richer data is sent."""
    value = {"tool": name, "grounded_reference": reference[:900]}
    if not isinstance(result, dict) or result.get("error"):
        return value
    if name == "get_presence_history":
        value.update(
            {
                k: result.get(k)
                for k in (
                    "available",
                    "state",
                    "period",
                    "timezone",
                    "scope",
                    "truncated",
                    "fresh",
                    "checked_at",
                    "source_snapshot_complete",
                )
            }
        )
        value["initial_states"] = result.get("initial_states", [])[:50]
        value["transitions"] = result.get("transitions", [])[:100]
        value["reported_away_intervals"] = result.get("reported_away_intervals", [])[:50]
    elif name == "get_personal_recommendation_context":
        value.update(
            {
                k: result.get(k)
                for k in ("topic", "preferences", "provenance", "missing", "scope", "state")
            }
        )
    elif name == "get_proactive_explanation":
        suggestion = result.get("suggestion") if isinstance(result.get("suggestion"), dict) else {}
        value.update(
            available=result.get("available") is True,
            reason=suggestion.get("reason"),
            kind=suggestion.get("kind"),
            topic=suggestion.get("topic"),
            feedback=suggestion.get("feedback"),
        )
    elif name in ("get_kitchen_ingredients", "get_meal_suggestions", "get_kitchen_plan"):
        value.update(
            {
                k: v
                for k, v in result.items()
                if k in ("state", "scope", "date", "meal", "page", "has_more")
            }
        )
        value["ingredients"] = [
            {k: r.get(k) for k in ("name", "quantity", "unit", "location", "best_by", "stale")}
            for r in result.get("items", [])[:12]
        ]
        value["suggestions"] = [
            {
                k: r.get(k)
                for k in ("name", "minutes", "missing", "use_soon", "taste_matches", "reason")
            }
            for r in result.get("suggestions", [])[:3]
        ]
        value["plans"] = result.get("plans", [])[:1]
        value["shopping"] = result.get("shopping", [])[:1]
        value["eating_out"] = result.get("eating_out", [])[:3]
        value["coaching_goals"] = result.get("coaching_goals", [])[:4]
        value["instruction"] = (
            "Suggest naturally from the recorded evidence, including missing ingredients or stale uncertainty. No invented stock, safety guarantees, purchases or shame. Coaching goals are optional, not obligations."
        )
    elif name == "get_chores":
        value["scope"] = result.get("scope")
        value["state"] = result.get("state")
        value["chores"] = [
            {
                **{k: item.get(k) for k in ("title", "due_at", "last_done_at", "enabled")},
                "rooms": [{k: r.get(k) for k in ("room", "floor")} for r in item.get("rooms", [])],
            }
            for item in result.get("items", [])[:8]
        ]
    elif name == "get_context_feed":
        value["scope"] = result.get("scope")
        value["source"] = result.get("queried_source")
        value["state"] = result.get("state")
        value["source_snapshot_complete"] = result.get("source_snapshot_complete")
        value["view"] = result.get("view", "current")
        value["more_available"] = result.get("next_offset") is not None
        value["records"] = [
            {
                "fresh": row.get("fresh"),
                "historical": row.get("historical", False),
                "observed_at": row.get("observed_at"),
                **{
                    k: v
                    for k, v in row.get("value", {}).items()
                    if k
                    in (
                        "unit",
                        "reports",
                        "transitions",
                        "minimum",
                        "maximum",
                        "mean_observed",
                        "window_seconds",
                        "change",
                        "summary",
                        "start_at",
                        "end_at",
                        "title",
                        "list",
                        "state",
                        "due",
                        "label",
                        "signal",
                        "category",
                        "room",
                        "current_temperature",
                        "target_temperature",
                        "action",
                        "type",
                        "show",
                        "start",
                        "end",
                    )
                    or (
                        result.get("queried_source") == "health"
                        and k in ("metric", "value", "sample_at")
                    )
                },
            }
            for row in result.get("items", [])[:12]
        ]
    elif name in ("get_trakt_watchlist", "get_watch_recommendations"):
        value.update(
            state=result.get("state"),
            scope=result.get("scope"),
            next_page=result.get("next_page"),
            records=[
                {
                    k: i.get(k)
                    for k in ("title", "year", "type", "genres", "runtime_minutes", "why_fit")
                }
                for i in result.get("items", [])[:20]
            ],
        )
        if name == "get_watch_recommendations":
            value.update(
                criteria=result.get("criteria"),
                availability=result.get("availability", "not_checked"),
                history_coverage=result.get("history_coverage", "unknown"),
                selection_instruction="Choose one supplied title and explain its evidence-backed fit naturally. Do not just read a list. Ask at most one useful follow-up if needed, and do not ask the user to repeat a known preference. No invented metadata, providers or guarantee they have never watched it.",
            )
    elif name == "get_home_activity":
        value["grounded_reference"] = (
            "Partial household evidence. State readings do not prove actions, people or chronology."
        )
        value["evidence_type"] = (
            "Recorded alerts and separate state readings, not a timeline of human activity"
        )
        value.update(
            period=result.get("period"),
            coverage=result.get("coverage"),
            recorded_event_counts=result.get("recorded_event_counts", [])[:20],
            count_scope=result.get("count_scope"),
            observations=[
                {"kind": i.get("kind"), "text": str(i.get("text", ""))[:160]}
                for i in result.get("observations", [])[:8]
                if i.get("kind") != "presence"
            ],
        )
    else:
        # Project human-facing fields only. Never forward transport config, IDs,
        # URLs, credentials, command arguments, logs or arbitrary nested objects.
        keys = (
            "title",
            "name",
            "body",
            "state",
            "status",
            "available",
            "active",
            "is_playing",
            "percent",
            "battery",
            "battery_percent",
            "battery_percentage",
            "firmware",
            "mode",
            "confirmed",
            "accepted",
            "already_there",
            "cancelled",
            "outcome",
            "coverage",
            "scope",
            "date",
            "start_date",
            "end_date",
            "timezone",
            "start",
            "end",
            "due_at",
            "ends_at",
            "remaining_seconds",
        )

        def display(k, v):
            if (
                k in ("start", "end", "due_at", "ends_at")
                and type(v) in (int, float)
                and v > 100000000
            ):
                try:
                    from .config import get_config

                    zone = ZoneInfo(
                        result.get("timezone") or get_config()["notifications"]["agenda_timezone"]
                    )
                    return datetime.fromtimestamp(v, zone).strftime("%a %b %d, %I:%M %p %Z")
                except (ValueError, OverflowError, OSError):
                    return "time unavailable"
            return v[:180] if isinstance(v, str) else v

        def project(item):
            return {
                k: display(k, v)
                for k, v in item.items()
                if k in keys and type(v) in (str, bool, int, float)
            }

        value["result"] = project(result)
        for key in ("events", "notifications", "reminders", "devices", "speakers", "locations"):
            if isinstance(result.get(key), list):
                value[key] = [project(i) for i in result[key][:6] if isinstance(i, dict)]
        for key in ("music", "tv"):
            if isinstance(result.get(key), dict):
                value[key] = project(result[key])
    if name == "get_companion_locations" and isinstance(result.get("room_cue"), dict):
        cue = result["room_cue"]
        value["room_cue"] = {
            k: cue.get(k) for k in ("room", "floor", "evidence", "identity", "expires_at")
        }
    while len(json.dumps(value).encode()) > 4000:
        lists = [k for k, v in value.items() if isinstance(v, list) and v]
        if not lists:
            break
        value[lists[-1]].pop()
    if name == "get_context_feed":
        value["more_available"] = result.get("next_offset") is not None or len(
            result.get("items", [])
        ) > len(value.get("records", []))
    return value


def preserve_scope(reply, name, result):
    if not isinstance(reply, str):
        return reply
    if name == "get_calendar_agenda" and result.get("available") and not result.get("events"):
        if not re.search(r"connected|calendar I can|feed|view", reply, re.I):
            reply += " That's only the calendar I can access."
        return reply
    if name == "get_proactive_explanation":
        suggestion = result.get("suggestion") if isinstance(result.get("suggestion"), dict) else {}
        reason = suggestion.get("reason")
        # The reason is already human-facing recorded evidence. Do not embellish
        # eligibility into a guessed mood, sensor event, person or hidden motive.
        if result.get("available") is True and isinstance(reason, str) and 1 <= len(reason) <= 500:
            return reason
        return "I don't have a recorded explanation for that check-in, so I shouldn't guess why it happened."
    if name == "get_watch_recommendations":
        if result.get("state") or not result.get("items"):
            from .watch_recommendations import fallback

            return fallback(result)
        return reply
    if name == "get_trakt_watchlist":
        if result.get("state"):
            return "I couldn't read your Trakt watchlist. Check its connection and private setup."
        if not result.get("items"):
            return "No titles were returned on this Trakt watchlist page; I haven't checked streaming availability."
        if not re.search(r"availab|streaming|where.*watch", reply, re.I):
            reply = reply.rstrip() + " Streaming availability hasn't been checked."
        return reply
    if name == "get_context_feed":
        if result.get("state"):
            return "That source is paused or has not been enabled; I haven't checked its records."
        if not result.get("items"):
            if result.get("queried_source") == "home_devices":
                return "I couldn't find a matching reading in the home sensors Amadeus follows. The sensor may not be selected, assigned to that room, or reporting."
            return "No matching records were returned from the selected feed. That does not establish there were none today."
        if (
            result.get("queried_source") == "home_devices"
            and result.get("view", "current") == "current"
            and all(row.get("fresh") is False for row in result["items"])
            and not re.search(r"\b(older|stale|previous|last|old)\b", reply, re.I)
        ):
            return "I only have older recorded readings from those sensors, so I can't confirm their current state."
        if result.get("queried_source") == "transit" and result.get("view", "current") == "current":
            reply = (
                reply.rstrip()
                + " This is the current selected feed, not a complete history of today."
            )
        return reply
    if name != "get_home_activity":
        return reply
    # Household context does not identify viewers/visitors or establish that a
    # home is empty. Remove affirmative person/occupancy claims; keep uncertainty.
    sentences = re.split(r"(?<!vs\.)(?<!Mr\.)(?<!Dr\.)(?<=[.!?])\s+", reply.strip())
    reply = " ".join(
        sentence
        for sentence in sentences
        if not (
            re.search(
                r"\b(someone|anyone|no one|nobody|people|visitors?|person|occupancy|empty house|you)\b",
                sentence,
                re.I,
            )
            and not re.search(
                r"unknown|unclear|can't|cannot|couldn't|not enough|no reliable|unavailable|estimate",
                sentence.replace("’", "'"),
                re.I,
            )
        )
    )
    if not reply:
        return ""
    reply = re.sub(
        r"(?:^|(?<=[.!?]))\s*No alerts (?:were triggered|triggered|occurred)\.\s*",
        " ",
        reply,
        flags=re.I,
    ).strip()
    if not re.search(
        r"record|report|logged|connected|history|reading|I (?:can|could|only)", reply, re.I
    ):
        reply = "From the connected records: " + reply
    if result.get("coverage") != "complete" and not re.search(
        r"partial|limited|only|all I can|can't|couldn't|cannot|don't|not enough|incomplete|missing|unavailable",
        reply.replace("’", "'"),
        re.I,
    ):
        reply = reply.rstrip() + " That's only the connected history I have."
    return reply


def acceptable(reply, name, result, reference):
    if not isinstance(reply, str) or not 1 <= len(reply.strip()) <= 500:
        return False
    reply = reply.replace("’", "'")
    if re.search(r"[{}<>]|tool_call|^\s*(assistant|system):", reply, re.I):
        return False
    if re.search(
        r"\b(all clear|everything is fine|nothing happened|house is safe|no unusual activity)\b",
        reply,
        re.I,
    ):
        return False
    if name == "get_watch_recommendations" and not result.get("state"):
        titles = [i.get("title", "") for i in result.get("items", [])]
        if titles and not any(t and t.casefold() in reply.casefold() for t in titles):
            return False
        # Availability and novelty are not supplied by a want-to-watch page.
        if re.search(
            r"\b(?:you(?:'ve| have) never (?:seen|watched)|definitely unwatched|you haven't (?:seen|watched))\b",
            reply,
            re.I,
        ):
            return False
        for sentence in re.split(r"(?<=[.!?])\s+", reply):
            if re.search(
                r"\b(?:available|stream(?:ing)?|watch on|on (?:netflix|hulu|prime|disney|peacock|hbo|apple tv))\b",
                sentence,
                re.I,
            ) and not re.search(
                r"unknown|not (?:been )?checked|haven't checked|can't verify|cannot verify|not verified",
                sentence,
                re.I,
            ):
                return False
        for quoted in re.findall(r'["“]([^"”]+)["”]', reply):
            if quoted.casefold() not in {t.casefold() for t in titles}:
                return False
        cue = re.search(
            r"\b(?:try|recommend|pick|start with|go with)\s+(?:(?:starting with|trying|watching|that you try)\s+)?[\"“']?(.+)",
            reply,
            re.I,
        )
        if cue and not any(cue[1].casefold().startswith(t.casefold()) for t in titles if t):
            return False
        supported_minutes = {i.get("runtime_minutes") for i in result.get("items", [])}
        supported_minutes.add(result.get("criteria", {}).get("max_minutes"))
        if any(
            int(v) not in supported_minutes
            for v in re.findall(r"\b(\d+)\s*[- ]?minutes?\b", reply, re.I)
        ):
            return False
    if name == "get_trakt_watchlist" and not result.get("state"):
        titles = [i.get("title", "") for i in result.get("items", [])]
        if titles and not any(t and t.casefold() in reply.casefold() for t in titles):
            return False
    if name == "get_home_activity":
        if re.search(
            r"turned (?:off|on)|someone (?:left|arrived)|stopped watching|closed the door",
            reply,
            re.I,
        ):
            return False
        if not re.search(
            r"record|report|logged|connected|history|reading|I (?:can|could|only)", reply, re.I
        ):
            return False
        if result.get("coverage") != "complete" and not re.search(
            r"partial|limited|only|all I can|can't|couldn't|cannot|don't|not enough|incomplete|not .{0,15}complete|missing|unavailable",
            reply,
            re.I,
        ):
            return False
    if (
        isinstance(result, dict)
        and result.get("error")
        and not re.search(r"fail|couldn't|cannot|can't|unavailable|trouble", reply, re.I)
    ):
        return False
    if name == "get_calendar_agenda":
        if re.search(r"^\s*Configured calendar feed\b|\(end exclusive\)", reply, re.I):
            return False
        if not result.get("available") and not re.search(
            r"unavailable|stale|can't|cannot|couldn't", reply, re.I
        ):
            return False
        if result.get("available"):
            events = result.get("events", [])
            if not events and not (
                re.search(
                    r"\b(no|none|nothing|not any|don't see|do not see|isn't|aren't)\b", reply, re.I
                )
                and re.search(r"\b(events?|appointments?|scheduled|calendar)\b", reply, re.I)
            ):
                return False
            if events and not any(
                str(e.get("title", ""))[:120].casefold() in reply.casefold()
                for e in events
                if e.get("title")
            ):
                return False
    if name == "get_companion_locations":
        names = [i.get("name", "") for i in result.get("locations", [])[:6]]
        if any(value and value.casefold() not in reply.casefold() for value in names):
            return False
    if name == "move_companion" and not result.get("already_there"):
        if re.search(r"arrived|I'm (?:at|on)|I am (?:at|on)|I moved", reply, re.I):
            return False
    if name == "control_spotify" and not re.search(
        r"request|asked|sent|accepted|confirm", reply, re.I
    ):
        return False
    if (
        name == "press_bot"
        and result.get("outcome") != "confirmed"
        and not re.search(r"check|uncertain|confirm", reply, re.I)
    ):
        return False
    # Exact new digits are usually invented measurements. Worded numbers and
    # semantic entailment still rely on the grounded prompt; this is not a proof.
    known = set(
        re.findall(r"\d+(?:\.\d+)?", json.dumps(facts(name, result, reference)) + reference)
    )
    for hour, minute in re.findall(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b", json.dumps(facts(name, result, reference)) + reference
    ):
        known.update((str(int(hour) % 12 or 12), str(int(hour)), str(int(minute)), minute))
    if set(re.findall(r"\d+(?:\.\d+)?", reply)) - known:
        return False
    return True

"""Bounded welcome-home cards from correlated presence events, never an LLM prompt."""

import json
import math
import threading
import time

QUIPS = {
    "kurisu": "Welcome back. The lab survived without adult supervision. Barely.",
    "okabe": "Welcome back. The lab has maintained this world line in your absence.",
    "sonic": "Welcome back! You handled outside. I handled the home stretch.",
    "pip": "Welcome home! I kept an eye on the little lab.",
}
_greeting_lock = threading.Lock()


def queue_greeting(
    inbox, policy, away_since=None, arrived_at=None, *, trigger="presence", recap_since=None
):
    # Both HA automations can submit concurrently to the threaded HTTP controller.
    with _greeting_lock:
        return _queue_greeting(inbox, policy, away_since, arrived_at, trigger, recap_since)


def _queue_greeting(inbox, policy, away_since, arrived_at, trigger, recap_since):
    now = time.time()
    if trigger not in ("presence", "door_after_time", "voice"):
        raise ValueError("Invalid arrival trigger")
    since = away_since if trigger == "presence" else recap_since
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (since, arrived_at)):
        raise ValueError("Invalid arrival timestamps")
    if not 0 <= now - arrived_at <= 180:
        raise ValueError("Arrival must be fresh")
    if trigger == "presence" and (
        recap_since is not None or not 120 <= arrived_at - since <= 90 * 86400
    ):
        raise ValueError("Arrival must be fresh after at least two minutes away")
    if trigger in ("door_after_time", "voice") and (
        away_since is not None or not 0 <= arrived_at - since <= 25 * 3600
    ):
        raise ValueError("Door welcome requires a bounded daily recap window")
    # Trust only a bounded timestamp window from the authenticated HA automation.
    # Do not read notification bodies or place event text into an LLM prompt.
    with inbox.connect() as db:
        # Presence and the convenience door rule may report the same opening.
        # Reuse the recent card even after delivery; never speak twice for that overlap.
        recent = db.execute(
            "SELECT payload FROM notifications WHERE dedupe LIKE 'arrival:%' AND created>=? "
            "ORDER BY created DESC LIMIT 1",
            (now - 180,),
        ).fetchone()
        if recent:
            return json.loads(recent[0])
        rows = db.execute(
            "SELECT payload FROM notifications WHERE created>=? AND created<=? AND due<=? "
            "AND priority>=2 AND status NOT IN ('cancelled','suppressed','dismissed') "
            "ORDER BY priority DESC,created DESC LIMIT 100",
            (since, arrived_at, now),
        ).fetchall()
    titles = []
    for (raw,) in rows:
        item = json.loads(raw)
        enabled = getattr(policy, "enabled_item", lambda value: policy.enabled(value["source"]))
        if item["source"] == "arrival" or not enabled(item):
            continue
        title = " ".join(item["title"].split())[:90]
        if title not in titles:
            titles.append(title)
    if titles:
        summary = (
            (" While you were away: " if trigger == "presence" else " Today's important updates: ")
            + "; ".join(titles[:3])
            + "."
        )
        if len(titles) > 3:
            summary += " More important updates are in your inbox."
    else:
        summary = (
            " No important updates were recorded while you were away."
            if trigger == "presence"
            else " No important updates were recorded today."
        )
    return inbox.publish(
        "arrival",
        "Welcome home",
        summary.strip()[:500],
        "important",
        ("voice-" + str(int(arrived_at // 180)))
        if trigger == "voice"
        else ("return-" if trigger == "presence" else "door-day-") + str(int(since)),
        expires_at=now + 180,
    )

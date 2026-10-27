"""Bounded welcome-home cards from correlated presence events, never an LLM prompt."""

import json
import math
import time
from .profiles import current_character

QUIPS = {
    "kurisu": "Welcome back. The lab survived without adult supervision. Barely.",
    "okabe": "Welcome back. The lab has maintained this world line in your absence.",
    "sonic": "Welcome back! You handled outside. I handled the home stretch.",
    "pip": "Welcome home! I kept an eye on the little lab.",
}


def queue_greeting(inbox, policy, away_since, arrived_at):
    now = time.time()
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (away_since, arrived_at)):
        raise ValueError("Invalid arrival timestamps")
    if not 0 <= now - arrived_at <= 180 or not 120 <= arrived_at - away_since <= 90 * 86400:
        raise ValueError("Arrival must be fresh after at least two minutes away")
    # Trust only a bounded timestamp window from the authenticated HA automation.
    # Do not read notification bodies or place event text into an LLM prompt.
    with inbox.connect() as db:
        rows = db.execute(
            "SELECT payload FROM notifications WHERE created>=? AND created<=? AND due<=? "
            "AND priority>=2 AND status NOT IN ('cancelled','suppressed','dismissed') "
            "ORDER BY priority DESC,created DESC LIMIT 100",
            (away_since, arrived_at, now),
        ).fetchall()
    titles = []
    for (raw,) in rows:
        item = json.loads(raw)
        if item["source"] == "arrival" or not policy.enabled(item["source"]):
            continue
        title = " ".join(item["title"].split())[:90]
        if title not in titles:
            titles.append(title)
    character = current_character().get("style", "pip")
    quip = QUIPS.get(character, QUIPS["pip"])
    if titles:
        summary = " While you were away: " + "; ".join(titles[:3]) + "."
        if len(titles) > 3:
            summary += " More important updates are in your inbox."
    else:
        summary = " No important updates were recorded while you were away."
    return inbox.publish(
        "arrival",
        "Welcome home",
        (quip + summary)[:500],
        "important",
        "return-" + str(int(away_since)),
        expires_at=now + 180,
    )

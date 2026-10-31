"""Bounded private conversational task state, never inherited action authority.

Only successful, application-validated read receipts may seed reusable query slots.
User/assistant prose remains quoted context; it does not become provider evidence or
permission for an action. State belongs to the enclosing expiring conversation and
must be cleared with it, not saved as a lasting user preference.
"""

from copy import deepcopy
import json
import re

VERSION = 1
MAX_STATE_BYTES = 1000

# Query slots are deliberately explicit. Credentials, provider responses, request
# identifiers and arbitrary model fields must not enter reusable routing context.
READ_ARGUMENTS = {
    "get_calendar_agenda": {"day", "start_date", "end_date"},
    "get_watch_recommendations": {"kind", "genre", "max_minutes", "page"},
    "get_trakt_watchlist": {"kind", "page"},
    "get_context_feed": {"source", "query", "view", "offset", "limit"},
    "get_recent_notifications": {"source", "status", "limit"},
    "get_home_activity": {"period"},
    "get_presence_history": {"period"},
    "get_personal_recommendation_context": {"topic"},
    "get_companion_locations": set(),
    "get_current_media": set(),
    "get_device_health": set(),
    "get_focus_session": set(),
    "get_chores": {"include_upcoming"},
    "get_proactive_explanation": set(),
    "list_reminders": set(),
    "list_spotify_devices": set(),
    "list_echo_speakers": set(),
    "get_bot_status": set(),
}
TOPICS = {
    "get_calendar_agenda": "calendar",
    "get_watch_recommendations": "watch_recommendation",
    "get_trakt_watchlist": "watch_library",
    "get_context_feed": "connected_feed",
    "get_recent_notifications": "notifications",
    "get_home_activity": "household_history",
    "get_personal_recommendation_context": "personal_ideas",
}
FOLLOWUP = re.compile(
    r"^\s*(?:and\b|what about\b|how about\b|instead\b|actually\b|no\b|not\b|"
    r"another\b|one more\b|same\b|make (?:that|it)\b|(?:a|an)\b.*\binstead\b)",
    re.I,
)
DATE_CUE = re.compile(
    r"\b(?:today|tomorrow|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"\d{1,2}(?:st|nd|rd|th)|\d{4}-\d{2}-\d{2})\b",
    re.I,
)
GENRES = (
    "science fiction",
    "science-fiction",
    "sci-fi",
    "scifi",
    "documentary",
    "animation",
    "adventure",
    "mystery",
    "romance",
    "thriller",
    "western",
    "fantasy",
    "history",
    "musical",
    "comedy",
    "horror",
    "family",
    "action",
    "drama",
    "crime",
    "music",
    "sport",
    "anime",
    "war",
)
RUNTIME = re.compile(
    r"\b(?:under|less than|up to|at most|within|maximum(?: of)?|no longer than)\s*"
    r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)\b",
    re.I,
)

# Direct-query inheritance is deliberately more conservative than model routing.
# Excluded utterances still reach the normal router; this does not deny read tools.
INHERITANCE_EXCLUSIONS = re.compile(
    r"\b(?:no|not|without|except|another question|another topic|different topic|one more question|same question|"
    r"hypothetically|pretend|imagine|suppose|quoting|quoted|someone said|they said|for example|"
    r"if I|if you|don't|do not|never|shouldn't|should not|wouldn't|would not|not now|no need to|"
    r"set|turn|pause|resume|start|stop|press|wave|snooze|dismiss|cancel|delete|send|speak|announce|move|"
    r"playing|paused|battery|charging|garage|thermostat|inbox|notifications?|transit|weather|"
    r"temperature|lights|volume|emergency|unsafe|hurt)\b|"
    r"\b(?:door|speaker|tv|television)\b.*\b(?:on|off|open|closed|state|status)\b|"
    r"(?:^|\s)(?:\"[^\"]+\"|'[^']+'|“[^”]+”)",
    re.I,
)
ELLIPTICAL_PICK = re.compile(
    r"\s*(?:(?:and|what about|how about)\s+)?(?:another|one more|the same|same)"
    r"(?:\s+(?:one|option|pick|recommendation|movie|film|show|series))?"
    r"(?:\s+(?:please|thanks|thank you))?[.!?]*\s*",
    re.I,
)


def _followup(text):
    return isinstance(text, str) and (
        bool(
            re.fullmatch(
                r"\s*(?:any genre|no genre (?:limit|restriction)|no time limit|any length)(?: now| please)?[.!?]*\s*",
                text,
                re.I,
            )
        )
        or bool(FOLLOWUP.search(text))
        or (len(text.split()) <= 30 and bool(re.search(r"\binstead[.!?]*\s*$", text, re.I)))
    )


def _media_patch_fragment(text):
    """Recognize a slot correction, not an arbitrary sentence mentioning a genre."""
    fragment = RUNTIME.sub(" ", text.casefold())
    for genre in GENRES:
        fragment = re.sub(r"(?<!\w)" + re.escape(genre) + r"(?!\w)", " ", fragment)
    fragment = re.sub(
        r"\b(?:movies?|films?|shows?|series|episodes?|any genre|no genre (?:limit|restriction)|"
        r"no time limit|any length|(?:runtime|length) (?:doesn't|does not) matter)\b",
        " ",
        fragment,
    )
    words = set(re.findall(r"[a-z]+(?:'[a-z]+)?|\d+", fragment))
    return words <= {
        "and",
        "what",
        "how",
        "about",
        "instead",
        "actually",
        "a",
        "an",
        "the",
        "one",
        "something",
        "please",
        "thanks",
        "thank",
        "you",
        "either",
        "or",
        "both",
        "all",
        "another",
        "more",
        "same",
        "for",
        "tonight",
        "now",
        "just",
        "kind",
        "genre",
    }


def _text(value, limit):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _arguments(tool, value):
    """Return a copied safe query shape, or None rather than truncate a query."""
    if not isinstance(value, dict):
        return None
    result = {}
    for key in READ_ARGUMENTS.get(tool, set()):
        if key not in value:
            continue
        item = value[key]
        if item is None or type(item) in (bool, int):
            result[key] = item
        elif isinstance(item, str) and len(item) <= 160:
            result[key] = item
        else:
            return None
    if len(json.dumps(result).encode()) > 500:
        return None
    return result


def normalize_state(value):
    """Accept only the bounded state contract; never trust persisted extra keys."""
    if not isinstance(value, dict) or value.get("version") != VERSION:
        return {}
    kind = value.get("kind")
    if kind not in ("read", "conversation"):
        return {}
    state = {
        "version": VERSION,
        "kind": kind,
        "topic": _text(value.get("topic"), 120),
        "constraints": {},
        "missing_slots": [
            _text(v, 40) for v in value.get("missing_slots", [])[:4] if isinstance(v, str)
        ]
        if isinstance(value.get("missing_slots", []), list)
        else [],
    }
    if kind == "read":
        tool = value.get("tool")
        if not isinstance(tool, str) or tool not in READ_ARGUMENTS:
            return {}
        arguments = _arguments(tool, value.get("arguments"))
        if arguments is None:
            return {}
        state.update(tool=tool, arguments=arguments)
        state["constraints"] = {
            k: deepcopy(v)
            for k, v in arguments.items()
            if k
            in {
                "kind",
                "genre",
                "max_minutes",
                "day",
                "start_date",
                "end_date",
                "period",
                "query",
                "status",
                "view",
            }
        }
        target = arguments.get("source")
        if target:
            state["target"] = {"kind": "source", "id": target}
    if len(json.dumps(state).encode()) > MAX_STATE_BYTES:
        return {}
    return state


def update_task_state(previous, *, user_text, calls=(), reply="", missing_slots=()):
    """Produce next state from actual call receipts or ordinary user discussion.

    Each receipt must be {name, arguments, success: True}; optional ``result`` and
    ``cancelled`` fields add fail-closed checks. The caller owns success validation.
    Unsuccessful calls and writes clear inherited read slots. The reply is accepted
    for integration convenience but is never parsed into facts, intent or authority.
    """
    prior = normalize_state(previous)
    receipts = list(calls) if isinstance(calls, (list, tuple)) else []
    successful_reads = []
    for call in receipts:
        if not isinstance(call, dict) or call.get("success") is not True or call.get("cancelled"):
            continue
        result = call.get("result")
        if isinstance(result, dict) and (result.get("error") or result.get("available") is False):
            continue
        name = call.get("name")
        if isinstance(name, str) and name in READ_ARGUMENTS:
            args = _arguments(name, call.get("arguments"))
            if args is not None:
                successful_reads.append((name, args, call.get("primary") is True))
    # Never retain a query behind any attempted action, including failed actions.
    if (
        receipts
        and all(
            isinstance(r, dict) and isinstance(r.get("name"), str) and r["name"] in READ_ARGUMENTS
            for r in receipts
        )
        and successful_reads
    ):
        selected = next((row for row in successful_reads if row[2]), successful_reads[-1])
        name, args, _ = selected
        return normalize_state(
            {
                "version": VERSION,
                "kind": "read",
                "topic": TOPICS.get(name, "connected_query"),
                "tool": name,
                "arguments": args,
                "missing_slots": list(missing_slots),
            }
        )
    if not receipts and prior.get("kind") == "conversation" and _followup(user_text):
        topic = prior.get("topic")
    else:
        topic = _text(user_text, 120)
    return normalize_state(
        {
            "version": VERSION,
            "kind": "conversation",
            "topic": topic,
            "missing_slots": list(missing_slots),
        }
    )


def resolve_read_followup(text, state):
    """Resolve explicit read-query corrections; never return a write operation.

    Calendar results carry ``requires_resolution=['calendar_window']``. The caller
    MUST replace the prior date arguments using the current text and fixed clock
    before executing; these results are context hints, not executable commands.
    Unknown constraints and unsupported exclusions fall back to ordinary routing.
    """
    state = normalize_state(state)
    if state.get("kind") != "read" or not isinstance(text, str) or not _followup(text):
        return None
    safety_text = re.sub(
        r"\b(?:no time limit|no genre (?:limit|restriction)|no longer than)\b",
        "",
        text,
        flags=re.I,
    )
    if INHERITANCE_EXCLUSIONS.search(safety_text):
        return None
    tool = state["tool"]
    args = deepcopy(state["arguments"])
    if tool == "get_calendar_agenda" and DATE_CUE.search(text):
        return {"name": tool, "arguments": args, "requires_resolution": ["calendar_window"]}
    if tool != "get_watch_recommendations":
        return None
    low = text.casefold()
    changed = False
    kind_mentions = []
    for kind, pattern in (
        ("movies", r"\b(?:movies?|films?)\b"),
        ("shows", r"\b(?:shows?|series|episodes?)\b"),
    ):
        for found in re.finditer(pattern, low):
            if not re.search(r"\b(?:not|no|without|except)\s+$", low[: found.start()]):
                kind_mentions.append(kind)
    if kind_mentions:
        kinds = set(kind_mentions)
        if len(kinds) == 1:
            args["kind"] = kinds.pop()
            changed = True
        elif not re.search(r"\b(?:either|both)\b", low):
            return None
    if re.search(r"\b(?:either movies? or shows?|both movies? and shows?)\b", low):
        args["kind"] = "all"
        changed = True
    matched = []
    for genre in GENRES:
        pattern = r"(?<!\w)" + re.escape(genre) + r"(?!\w)"
        for found in re.finditer(pattern, low):
            if re.search(r"\b(?:not|no|without|except)\s+$", low[: found.start()]):
                continue
            matched.append(genre)
    if matched:
        from .watch_recommendations import genre_key

        genres = {genre_key(g) for g in matched}
        if len(genres) != 1:
            return None
        args["genre"] = genres.pop()
        changed = True
    elif any(
        re.search(r"\b(?:not|no|without|except)\s+" + re.escape(g) + r"\b", low) for g in GENRES
    ):
        return None
    if re.search(
        r"\b(?:any genre|no genre (?:limit|restriction)|genre (?:doesn't|does not) matter)\b", low
    ):
        args.pop("genre", None)
        changed = True
    if re.search(r"\b(?:longer|more) than\s*\d+\s*(?:minutes?|mins?|hours?|hrs?)\b", low):
        return None  # The current recommendation API has no minimum-runtime slot.
    runtime = list(RUNTIME.finditer(low))
    if len(runtime) > 1:
        return None
    if runtime:
        match = runtime[0]
        value = float(match[1]) * (60 if match[2].startswith(("hour", "hr")) else 1)
        if not value.is_integer() or not 1 <= value <= 600:
            return None
        args["max_minutes"] = int(value)
        changed = True
    if re.search(
        r"\b(?:no time limit|any length|(?:runtime|length) (?:doesn't|does not) matter)\b", low
    ):
        args.pop("max_minutes", None)
        changed = True
    if (changed and not _media_patch_fragment(text)) or (
        not changed and not ELLIPTICAL_PICK.fullmatch(text)
    ):
        return None
    # A new query starts on its first page; old pagination is not a taste constraint.
    args["page"] = 1
    return {"name": tool, "arguments": args}


def context_for_turn(text, state=None, history=()):
    """Quote bounded task/dialogue data without treating it as instructions."""
    recent = []
    for message in list(history or [])[-4:]:
        if isinstance(message, dict) and message.get("role") in ("user", "assistant"):
            recent.append({"role": message["role"], "content": _text(message.get("content"), 500)})
    return {
        "current_request": _text(text, 2000),
        "recent_dialogue": recent,
        "task_state": normalize_state(state),
    }

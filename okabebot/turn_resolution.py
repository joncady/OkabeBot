"""Deterministic turn slots. No provider reads, inferred targets or authorization.

Calendar windows are local civil dates with exclusive API end boundaries. Spoken
ranges using through/to/between include their last day; an explicitly exclusive
end or ``until`` does not. Notification changes are PATCH-shaped: only fields
explicitly requested by the current user are returned.
"""

import calendar
import datetime as dt
import re
import time
from zoneinfo import ZoneInfo


class ResolutionError(ValueError):
    """A recognized request needs clarification before execution."""


MONTHS = {
    name.casefold(): index
    for index in range(1, 13)
    for name in (calendar.month_name[index], calendar.month_abbr[index])
}
MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))
WEEKDAYS = {name.casefold(): i for i, name in enumerate(calendar.day_name)}
WEEKDAY_PATTERN = "|".join(WEEKDAYS)
FOLLOWUP = r"^\s*(?:and|or|what about|how about|instead|what of)\b"
ISO_DATE = r"\b\d{4}-\d{2}-\d{2}\b"
NATURAL_DATE = rf"\b(?P<month>{MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?\b"


def _window(start, end):
    if not 0 < (end - start).days <= 366:
        raise ResolutionError(
            "Choose a calendar range of 1–366 days with its last day after its first."
        )
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def _date(year, month, day):
    try:
        return dt.date(year, month, day)
    except ValueError:
        raise ResolutionError(
            "That calendar date does not exist. Which date did you mean?"
        ) from None


def _task_start(task):
    if not isinstance(task, dict) or task.get("tool") not in (
        "get_calendar_agenda",
        "show_calendar_agenda",
    ):
        return None
    args = task.get("arguments", {})
    try:
        start = dt.date.fromisoformat(args["start_date"])
        end = dt.date.fromisoformat(args["end_date"])
        return start if 0 < (end - start).days <= 7 else None
    except (ValueError, TypeError, KeyError):
        return None


def calendar_window(text, *, now=None, timezone="local", task=None):
    """Return an authoritative date window, or {} when no date expression is known.

    Bare weekdays mean the next occurrence including today. ``This Thursday``
    uses this ISO week; ``next Thursday`` uses next ISO week. A short follow-up
    inherits a prior calendar task's week/month only for a <=7-day prior window.
    Natural month/day dates without years use the local current year; an omitted
    year on a range's second month may roll over into the following year.
    """
    now = time.time() if now is None else now
    local = dt.datetime.fromtimestamp(now, dt.timezone.utc).astimezone(
        None if timezone == "local" else ZoneInfo(timezone)
    )
    today = local.date()
    value = text.casefold().replace("’", "'")
    requested = _unquoted(value)
    if re.search(r"\b(not|instead of|rather than|except|excluding)\b", requested):
        raise ResolutionError("Please state the one requested calendar date or range directly.")
    keyed = {
        key: re.search(rf"""\b{key}["']?\s*[:=]\s*["']?({ISO_DATE})""", value)
        for key in ("start_date", "end_date")
    }
    if any(keyed.values()):
        if not all(keyed.values()):
            raise ResolutionError("Provide both start_date and exclusive end_date.")
        if any(
            requested[match.start() : match.start() + len(key)] != key
            for key, match in keyed.items()
        ):
            raise ResolutionError("State the requested API date keys outside quoted source text.")
        try:
            return _window(*(dt.date.fromisoformat(keyed[k][1]) for k in keyed))
        except ValueError as exc:
            raise ResolutionError("Choose valid ISO start_date and exclusive end_date.") from exc
    value = requested
    points = []
    for match in re.finditer(ISO_DATE, value):
        try:
            day = dt.date.fromisoformat(match.group())
        except ValueError:
            raise ResolutionError(
                "That ISO date does not exist. Which date did you mean?"
            ) from None
        points.append((match.start(), match.end(), day, True))
    for match in re.finditer(NATURAL_DATE, value):
        # Defer omitted-year validation until an explicit endpoint year is inherited.
        day = _date(int(match["year"] or 2000), MONTHS[match["month"]], int(match["day"]))
        points.append((match.start(), match.end(), day, bool(match["year"])))
    points.sort()
    if len(points) > 2:
        raise ResolutionError("Please choose one continuous calendar range.")
    if points:
        if re.search(r"\b(today|tomorrow|this week|next week|this month|next month)\b", value):
            raise ResolutionError("Please choose the relative date or the explicit date range.")
        first = points[0]
        if len(points) == 1:
            start = first[2] if first[3] else _date(today.year, first[2].month, first[2].day)
            # Same-month shorthand: June 10 through 12, including ordinal suffixes.
            tail = value[first[1] :]
            match = re.match(
                r"\s*(?:through|thru|to|until|and|[–—-])\s*(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b",
                tail,
            )
            if match:
                if re.search(r"\band\b", match.group()) and not re.search(
                    r"\bbetween\b", value[: first[0]]
                ):
                    raise ResolutionError("Are those separate dates or one continuous range?")
                last = _date(start.year, start.month, int(match[1]))
                exclusive = "until" in match.group() or bool(re.search(r"\bexclusive\b", value))
                return _window(start, last + dt.timedelta(days=not exclusive))
            return _window(start, start + dt.timedelta(days=1))
        second = points[1]
        connector = value[first[1] : second[0]]
        range_words = bool(re.search(r"\b(through|thru|to|until)\b|[–—-]", connector))
        between = bool(
            re.search(r"\bbetween\b", value[: first[0]]) and re.search(r"\band\b", connector)
        )
        if not (range_words or between):
            raise ResolutionError("Are those separate dates or one continuous calendar range?")
        start_year = first[2].year if first[3] else second[2].year if second[3] else today.year
        end_year = second[2].year if second[3] else start_year
        if not first[3] and second[3] and first[2].month > second[2].month:
            start_year -= 1
        if not second[3] and second[2].month < first[2].month:
            end_year += 1
        start = _date(start_year, first[2].month, first[2].day)
        end = _date(end_year, second[2].month, second[2].day)
        exclusive = bool(re.search(r"\b(until|exclusive)\b", connector + " " + value[second[1] :]))
        return _window(start, end + dt.timedelta(days=not exclusive))

    weekdays = list(re.finditer(rf"\b(?:(this|next)\s+)?({WEEKDAY_PATTERN})\b", value))
    if weekdays:
        if len(weekdays) > 2:
            raise ResolutionError("Please choose one calendar day or continuous range.")
        anchor = _task_start(task) if re.search(FOLLOWUP, value) else None
        if (
            re.search(FOLLOWUP, value)
            and isinstance(task, dict)
            and task.get("tool") in ("get_calendar_agenda", "show_calendar_agenda")
            and task.get("arguments", {}).get("start_date")
            and anchor is None
            and not weekdays[0][1]
        ):
            raise ResolutionError("Which week should that weekday refer to?")

        def resolve(match):
            weekday = WEEKDAYS[match[2]]
            if match[1] == "this":
                return today - dt.timedelta(days=today.weekday()) + dt.timedelta(days=weekday)
            if match[1] == "next":
                return today + dt.timedelta(days=7 - today.weekday() + weekday)
            if anchor:
                return anchor - dt.timedelta(days=anchor.weekday()) + dt.timedelta(days=weekday)
            return today + dt.timedelta(days=(weekday - today.weekday()) % 7)

        start = resolve(weekdays[0])
        if len(weekdays) == 1:
            return _window(start, start + dt.timedelta(days=1))
        connector = value[weekdays[0].end() : weekdays[1].start()]
        if not re.search(r"\b(through|thru|to|until)\b|[–—-]", connector) and not (
            "between" in value[: weekdays[0].start()] and "and" in connector
        ):
            raise ResolutionError("Are those separate weekdays or one continuous range?")
        end = resolve(weekdays[1])
        if end < start and not weekdays[1][1]:
            end += dt.timedelta(days=7)
        return _window(start, end + dt.timedelta(days="until" not in connector))

    if re.search(r"\btoday\b", value) and re.search(r"\btomorrow\b", value):
        if re.search(r"\b(?:through|to|between)\b", value):
            return _window(today, today + dt.timedelta(days=2))
        raise ResolutionError("Do you mean today, tomorrow, or both days?")
    if re.search(FOLLOWUP, value):
        match = re.search(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b", value)
        anchor = _task_start(task)
        if match and anchor:
            day = _date(anchor.year, anchor.month, int(match[1]))
            return _window(day, day + dt.timedelta(days=1))
    if re.search(r"\bnext month\b", value):
        start = (today.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        return _window(start, end)
    from .agenda import conversation_range

    result = conversation_range(value, now=now, timezone=timezone)
    if not result and (
        re.search(ISO_DATE, text)
        or re.search(NATURAL_DATE, text, re.I)
        or re.search(rf"\b(?:{WEEKDAY_PATTERN}|today|tomorrow|this week|next week)\b", text, re.I)
    ):
        raise ResolutionError(
            "Please state the requested calendar date outside quoted source text."
        )
    return result


_LITERAL = r"""(?:"([^"\n]+)"|'([^'\n]+)'|([A-Za-z0-9](?:[A-Za-z0-9_.:@+-]*[A-Za-z0-9_:@+-])?))"""
_COMMAND = re.compile(
    r"^\s*(?:please\s+help\s*:\s*)?(?:please\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:(?:i(?:'d| would) like|i want)\s+(?:you\s+)?to\s+)?"
    r"(?:(?:for|on)\s+[^,;:\n]+[,;:]\s*)?"
    r"(make|set|disable|enable|mute|unmute|silence|turn|resume|stop|pause|allow|block|keep)\b",
    re.I,
)
_STOP_IDS = {
    "keep",
    "all",
    "my",
    "the",
    "these",
    "those",
    "your",
    "disable",
    "enable",
    "mute",
    "unmute",
    "silence",
    "set",
    "make",
    "turn",
    "stop",
    "pause",
    "resume",
}


def _target_spans(patterns, text):
    found = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            group = next((i for i, value in enumerate(match.groups(), 1) if value is not None), 0)
            literal = match[group].strip()
            if literal.casefold() not in _STOP_IDS:
                found.append((literal, *match.span(group)))
    return found


def _targets(patterns, text):
    return list(dict.fromkeys(row[0] for row in _target_spans(patterns, text)))


def notification_intent(text):
    """Resolve explicit source/sender notification configuration into a PATCH call.

    Source and sender IDs occupy separate spans. A sender-only phrase never names
    a source. Quoted reports, how-to questions and negation are not authorization.
    Return {} for non-configuration turns; clarify a recognized incomplete command.
    """
    if not isinstance(text, str):
        return {}
    value = text.replace("’", "'")
    pause = notification_pause(value)
    if pause:
        return pause
    command = _COMMAND.search(value)
    if not command or not re.search(r"\b(alerts?|notifications?|sender)\b", value, re.I):
        return {}
    if not re.search(r"\b(alerts?|notifications?|sender)\b", _unquoted(value), re.I):
        return {}
    source_spans = _target_spans(
        [
            rf"\b(?:source|provider)\s*(?:[:=]\s*)?{_LITERAL}",
            rf"{_LITERAL}\s+\b(?:alerts?|notifications?)\b",
            rf"\b(?:alerts?|notifications?)\s+(?:from|for|on)\s+(?!sender\b){_LITERAL}",
            rf"\b(?:for|on)\s+{_LITERAL}(?=\s+sender\b)",
        ],
        value,
    )
    sender_spans = _target_spans([rf"\bsender(?:_id|\s+id)?\s*(?:[:=]\s*)?{_LITERAL}"], value)
    sources = list(dict.fromkeys(row[0].casefold() for row in source_spans))
    senders = list(dict.fromkeys(row[0] for row in sender_spans))
    if len(sources) != 1:
        raise ResolutionError("Name one notification source separately from the sender ID.")
    if len(senders) > 1:
        raise ResolutionError("Choose one exact sender ID for this change.")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,29}", sources[0]):
        raise ResolutionError("Please name the notification source ID shown in the inbox.")
    fields = {}
    # Remove literal identities before interpreting option words inside the command.
    options = value
    for start, end in sorted({row[1:] for row in source_spans + sender_spans}, reverse=True):
        options = options[:start] + " TARGET " + options[end:]
    # Consume a deliberately closed configuration grammar after exact identity
    # spans are removed. Unknown qualifier, scheduling, exception or action text
    # must not silently become an unconditional source-wide update.
    _, segments = _quote_mask(options)
    option_words = {
        "target",
        "enabled",
        "disabled",
        "silent",
        "chime",
        "speech",
        "spoken",
        "default",
        "urgent",
        "important",
        "normal",
        "low",
    }
    for start, end, closed in segments:
        if not closed or options[start + 1 : end - 1].strip().casefold() not in option_words:
            raise ResolutionError("Quoted text is not a notification configuration value.")
    supported = option_words | {
        "keep",
        "but",
        "their",
        "sound",
        "is",
        "please",
        "help",
        "can",
        "could",
        "would",
        "will",
        "you",
        "i",
        "i'd",
        "like",
        "want",
        "to",
        "for",
        "on",
        "from",
        "the",
        "my",
        "this",
        "that",
        "a",
        "an",
        "all",
        "with",
        "and",
        "source",
        "provider",
        "sender",
        "id",
        "alert",
        "alerts",
        "notification",
        "notifications",
        "make",
        "set",
        "disable",
        "enable",
        "mute",
        "unmute",
        "silence",
        "turn",
        "resume",
        "stop",
        "pause",
        "allow",
        "block",
        "off",
        "audio",
        "sound",
        "priority",
        "is",
        "no",
        "without",
        "chimes",
        "read",
        "aloud",
        "speak",
        "now",
        "immediately",
        "permanently",
        "thanks",
        "thank",
    }
    if set(re.findall(r"[\w]+(?:'[\w]+)?", options.casefold())) - supported:
        raise ResolutionError(
            "Please choose one immediate notification setting without qualifiers."
        )
    if re.search(
        r"\b(don't|do not|never|hypothetically|pretend|imagine|not|unless|except|if|after|before|until|when|while|tomorrow|tonight|later)\b"
        r"|\bat\s+\d|\bfor\s+(?:\d+|one|two|three|four|five|ten)\s+(?:minutes?|hours?|days?)\b",
        options,
        re.I,
    ):
        raise ResolutionError("Please choose an immediate, unconditional notification setting.")
    if re.search(r"\b(disable|disabled|block|stop|pause)\b|\bturn\b.*\boff\b", options, re.I):
        fields["enabled"] = False
    if re.search(r"\b(enable|enabled|allow|resume)\b|\bturn\b.*\bon\b", options, re.I):
        if "enabled" in fields:
            raise ResolutionError(
                "Choose whether this notification rule should be enabled or disabled."
            )
        fields["enabled"] = True
    audio = set()
    if re.search(r"\b(silent|silence|mute)\b|\b(?:no|without) sound\b", options, re.I):
        audio.add("silent")
    if re.search(r"\b(chime|chimes)\b", options, re.I):
        audio.add("chime")
    if re.search(r"\b(speech|spoken|read aloud|speak)\b", options, re.I):
        audio.add("speech")
    if re.search(
        r"\bunmute\b|\b(?:audio|sound)\s+(?:to\s+)?default\b|\bdefault\s+(?:audio|sound)\b",
        options,
        re.I,
    ):
        audio.add("default")
    if len(audio) > 1:
        raise ResolutionError("Choose one audio mode for this notification rule.")
    if audio:
        fields["audio"] = audio.pop()
    priorities = _targets(
        [
            r"\bpriority\s*(?:(?:to|is)\s+|[:=]\s*)?(urgent|important|normal|low|default)\b",
            r"\b(urgent|important|normal|low|default)\s+priority\b",
            r"\b(?:make|set)\b.{0,180}?\b(urgent|important|normal|low)\s*[.!?]*$",
        ],
        options,
    )
    if len(priorities) > 1:
        raise ResolutionError("Choose one notification priority.")
    if priorities:
        fields["priority"] = priorities[0].casefold()
    if not fields:
        raise ResolutionError(
            "Which notification setting should change: enabled, audio or sender priority?"
        )
    if not senders and "priority" in fields:
        raise ResolutionError("Priority changes need one exact sender ID.")
    arguments = {"source": sources[0], **({"sender_id": senders[0]} if senders else {}), **fields}
    return {
        "name": "set_sender_notification_rule" if senders else "set_notification_source",
        "arguments": arguments,
    }


def notification_arguments(text, name, arguments, *, current_rule=None):
    """Validate identity/scope and strip model-invented options from a rule update.

    PATCH callers omit current_rule. A legacy full-update caller may supply its
    authoritative current rule so omitted fields are preserved instead of reset.
    This helper does not authorize a tool; caller permissions still apply.
    """
    resolved = notification_intent(text)
    if not resolved or resolved["name"] != name:
        raise ResolutionError(
            "Please specify a source-wide rule or an exact source and sender rule."
        )
    if not isinstance(arguments, dict):
        raise ResolutionError("Please provide structured notification settings.")
    for field in ("source", "sender_id"):
        supplied = arguments.get(field)
        if field == "source" and isinstance(supplied, str):
            supplied = supplied.casefold()
        if field in arguments and supplied != resolved["arguments"].get(field):
            raise ResolutionError(
                "The notification target does not match the source and sender you named."
            )
    result = dict(resolved["arguments"])
    if current_rule is not None:
        for field in ("enabled", "audio", "priority"):
            if (
                field not in result
                and field in current_rule
                and (field != "priority" or "sender_id" in result)
            ):
                result[field] = current_rule[field]
    return result


# The user's current speech act is distinct from words inside a quoted message.
_ACTION_DOMAINS = {
    "move_companion": ({"move", "come", "go", "return", "send", "head", "travel"}, None),
    "set_speaker_volume": (
        {"set", "turn", "lower", "raise", "reduce", "increase", "mute", "unmute", "make"},
        r"\b(volume|speaker|mute|unmute)\b",
    ),
    "control_spotify": (
        {"play", "resume", "start", "pause", "stop", "skip", "next", "previous", "go"},
        r"\bspotify\b",
    ),
    "control_focus_session": (
        {"start", "begin", "set", "cancel", "stop", "end", "give"},
        r"\b(focus|timer)\b",
    ),
    "press_bot": ({"press", "wave"}, r"\b(switch\s*bot|wave)\b"),
    "speak_on_echo": ({"say", "speak", "tell", "announce", "read"}, None),
    "snooze_notifications": (
        {"snooze", "hold", "pause", "resume", "let"},
        r"\b(alerts?|notifications?)\b",
    ),
    "dismiss_notification": ({"dismiss", "clear"}, r"\b(alerts?|notifications?|cards?|inbox)\b"),
    "create_reminder": ({"remind", "create", "set", "add", "schedule"}, r"\b(remind|reminders?)\b"),
    "cancel_reminder": ({"cancel", "delete", "remove"}, r"\breminders?\b"),
    "show_calendar_agenda": (
        {"show", "display", "put", "bring"},
        r"\b(calendar|agenda|schedule)\b",
    ),
}
_REQUEST_PREFIX = re.compile(
    r"^\s*(?:please\s+help\s*:\s*)?(?:please\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:(?:i(?:'d| would) like|i want)\s+(?:you\s+)?to\s+)?",
    re.I,
)


def _quote_mask(text):
    """Mask quoted payloads while preserving offsets and apostrophes in names."""
    text = text.replace("’", "'")
    result = list(text)
    closing = None
    escaped = False
    start = None
    segments = []
    for index, char in enumerate(text):
        if closing is not None:
            result[index] = " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == closing and not (
                char == "'"
                and index > 0
                and index + 1 < len(text)
                and text[index - 1].isalnum()
                and text[index + 1].isalnum()
            ):
                closing = None
                segments.append((start, index + 1, True))
        elif char in ('"', "“", "‘") or (
            char == "'" and (index == 0 or not text[index - 1].isalnum())
        ):
            closing = {"“": "”", "‘": "'"}.get(char, char)
            start = index
            result[index] = " "
    if closing is not None:
        segments.append((start, len(text), False))
    return "".join(result), segments


def _unquoted(text):
    return _quote_mask(text)[0]


def operational_text(text):
    """Authority checks ignore quoted payloads; raw text remains available for slots."""
    return _unquoted(text)


def notification_pause(text):
    value = text.strip().casefold().rstrip(".!?")
    value = re.sub(r"^(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:please\s+)?", "", value)
    if re.fullmatch(
        r"(?:let (?:notifications|alerts) through again|resume (?:notifications|alerts))", value
    ):
        return {"name": "snooze_notifications", "arguments": {"minutes": 0}}
    match = re.fullmatch(r"(?:hold|pause|snooze) (?:notifications|alerts) for (.+)", value)
    if not match:
        return {}
    duration = match[1]
    if duration in ("an hour and a half", "one and a half hours"):
        minutes = 90
    else:
        found = re.fullmatch(r"(\d+|a|an|one|two|three|half) (minutes?|hours?)", duration)
        if not found:
            return {}
        number = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "half": 0.5}.get(found[1])
        minutes = (number if number is not None else int(found[1])) * (
            60 if found[2].startswith("hour") else 1
        )
    if not 1 <= minutes <= 1440 or not float(minutes).is_integer():
        raise ResolutionError("Choose a notification pause between one minute and one day.")
    return {"name": "snooze_notifications", "arguments": {"minutes": int(minutes)}}


def _primary_command(text):
    if not isinstance(text, str):
        raise ResolutionError("Please state one action directly.")
    value = _unquoted(text)
    start = _REQUEST_PREFIX.match(value).end()
    rest = value[start:]
    scoped = re.match(r"\s*(?:on|for|at|in)\b[^,;:\n]+[,;:]\s*", rest, re.I)
    scope = ""
    if scoped:
        scope = scoped.group().strip().rstrip(",;:").strip()
        start += scoped.end()
    match = re.match(r"\s*([a-z]+)\b", value[start:], re.I)
    if not match:
        raise ResolutionError("Please state one action directly.")
    return value, match[1].casefold(), start + match.end(), scope


def assert_action_request(text, name):
    """Require an imperative/polite current-user speech act for this tool domain.

    This is a grounding guard, not permission or argument validation. Reports,
    quotations, how-to questions and another tool's message payload grant no
    authority. Registered names, numeric slots and caller permissions must still
    be checked separately.
    """
    if name in ("set_notification_source", "set_sender_notification_rule"):
        intent = notification_intent(text)
        if not intent or intent["name"] != name:
            raise ResolutionError("Please specify that notification change directly.")
        return
    if name == "snooze_notifications" and notification_pause(text):
        return
    if name not in _ACTION_DOMAINS:
        raise ResolutionError("That action has no current-request grounding rule.")
    value, verb, end, scope = _primary_command(text)
    verbs, domain = _ACTION_DOMAINS[name]
    imperative = value[_REQUEST_PREFIX.match(value).end() :]
    if (
        verb == "give"
        and name == "control_focus_session"
        and not re.fullmatch(
            r"\s*give me (?:a |an )?\d+[ -](?:minute|minutes) focus (?:block|session|timer)[.!?]*\s*",
            imperative,
            re.I,
        )
    ):
        raise ResolutionError("State a duration and focus block directly.")
    if (
        verb == "go"
        and name == "control_spotify"
        and not re.fullmatch(
            r"\s*go to (?:the )?(?:next|previous) spotify track[.!?]*\s*", imperative, re.I
        )
    ):
        raise ResolutionError("Please request the Spotify playback action directly.")
    if verb not in verbs or (domain and not re.search(domain, value, re.I)):
        raise ResolutionError("Please request that device or action directly, outside quoted text.")
    if scope:
        if name == "speak_on_echo":
            if not re.match(r"^(?:on|at)\b", scope, re.I):
                raise ResolutionError(
                    "Please name the speaker with an explicit On <speaker> command."
                )
        else:
            remaining = re.sub(r"^\s*(?:on|for|at|in)\s+", "", scope, flags=re.I)
            if domain:
                remaining = re.sub(domain, " ", remaining, flags=re.I)
                remaining = re.sub(
                    r"\b(the|my|this|that|settings|session)\b", " ", remaining, flags=re.I
                )
            if not domain or remaining.strip():
                raise ResolutionError("Please name that action's device scope directly.")
    if (
        name == "speak_on_echo"
        and verb == "tell"
        and re.match(r"\s*(?:me|us|about)\b", value[end:], re.I)
    ):
        raise ResolutionError("Please name the speaker as a destination, not a topic.")
    if re.search(
        r"\b(whenever|during|when|unless|if|provided|assuming|every|each|daily|weekly|monthly|yearly|hourly|repeatedly)\b|\bonce\s+(?!now\b)\w+|\bas soon as\b",
        value,
        re.I,
    ):
        raise ResolutionError(
            "Conditional or recurring actions are not supported; state one action."
        )
    clock = (
        r"\b(?:at|by)\s+(?:(?:about|around)\s+)?"
        r"(?:\d|one\b|two\b|three\b|four\b|five\b|six\b|seven\b|eight\b|nine\b|ten\b|eleven\b|twelve\b|half\b|quarter\b|noon\b|midnight\b|bedtime\b|sunrise\b|sunset\b)"
        r"|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b"
    )
    if re.search(clock, value, re.I):
        raise ResolutionError("Clock-scheduled actions need an explicit supported time workflow.")
    if name != "show_calendar_agenda" and re.search(
        rf"\b(?:{WEEKDAY_PATTERN}|{MONTH_PATTERN}|today|tomorrow|tonight|later|eventually|next\s+week|next\s+month)\b|{ISO_DATE}",
        value,
        re.I,
    ):
        raise ResolutionError("Day-scheduled actions need an explicit supported time workflow.")
    if name != "create_reminder":
        duration_prepositions = (
            "in" if name in ("snooze_notifications", "show_calendar_agenda") else "in|for"
        )
        unsupported_bounds = (
            "later|eventually|tonight"
            if name == "show_calendar_agenda"
            else "after|before|until|later|eventually|tonight"
        )
        if re.search(
            rf"\b(?:{duration_prepositions})\s+(?:[\w-]+\s+){{0,5}}(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b|\b(?:{unsupported_bounds})\b",
            value,
            re.I,
        ):
            raise ResolutionError("Scheduled actions are not supported; state an immediate action.")
    if name != "speak_on_echo" and re.search(
        r"\b(don't|do not|never|hypothetically|pretend|imagine|unless|if|when)\b", value, re.I
    ):
        raise ResolutionError("Please state an unconditional action directly.")
    if (
        name == "move_companion"
        and verb == "send"
        and re.match(
            r"\s*(?:an?\s+)?(?:message|announcement|notification|reminder|audio|speech)\b",
            value[end:],
            re.I,
        )
    ):
        raise ResolutionError("Sending a message is not moving the character.")


def _name_at(text, names):
    """Longest full registered name at the start of an explicit destination slot."""
    results = []
    for name in names:
        literal = r"\s+".join(re.escape(piece) for piece in name.replace("’", "'").split())
        match = re.match(rf"""\s*(?:the\s+)?["'“‘]?({literal})(?!\w)["'”’]?""", text, re.I)
        if match:
            results.append((match.end(), name))
    return max(results, default=None)


def resolve_named_speaker(text, requested, names):
    """Resolve one explicit canonical registered destination, never an alias guess.

    Quoted speech content cannot supply the destination. A quoted name in an
    explicit destination slot is allowed. Case/spacing and apostrophe typography
    are equivalent; registry names themselves remain the returned canonical text.
    ``requested`` is model output and cannot supply missing user authority.
    """
    assert_action_request(text, "speak_on_echo")
    if not isinstance(requested, str):
        raise ResolutionError("Choose one registered speaker name.")
    names = list(names)
    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ResolutionError("No valid speaker name registry is available.")
    keys = [" ".join(name.replace("’", "'").casefold().split()) for name in names]
    if len(keys) != len(set(keys)):
        raise ResolutionError("Speaker names must be unambiguous in the registry.")
    raw = text.replace("’", "'")
    unquoted, verb, end, scope = _primary_command(raw)
    if scope:
        scope_start = _REQUEST_PREFIX.match(unquoted).end()
        scope_raw = raw[scope_start:]
        scope_name = _name_at(re.sub(r"^\s*(?:on|at)\s+", "", scope_raw, flags=re.I), names)
        if scope_name is None:
            raise ResolutionError("Name one registered speaker in the fronted destination scope.")
    candidates = []
    # Explicit routing prepositions, including a fronted `On <speaker>, say ...`.
    for match in re.finditer(r"\b(?:on|through|via|using|to|at|for)\b", unquoted, re.I):
        destination = raw[match.end() :]
        selected = _name_at(destination, names)
        if selected:
            stop, canonical = selected
            tail = destination[stop:]
            # Remaining unquoted prose belongs to the spoken message, not a target slot.
            if not tail.strip() or re.match(r"""\s*[,;:.!?"'“‘]""", tail):
                candidates.append(canonical)
            elif re.match(r"\s+(?:and|or)\b", tail, re.I):
                raise ResolutionError("Please choose exactly one speaker for this announcement.")
    # `Tell <registered speaker> ...` has an explicit direct-object destination.
    if verb == "tell":
        selected = _name_at(raw[end:], names)
        if selected:
            stop, canonical = selected
            if re.match(r"\s+(?:and|or)\b", raw[end + stop :], re.I):
                raise ResolutionError("Please choose exactly one speaker for this announcement.")
            candidates.append(canonical)
    unique = list(dict.fromkeys(candidates))
    if len(unique) != 1:
        raise ResolutionError("Name exactly one registered speaker outside the spoken message.")
    return unique[0]

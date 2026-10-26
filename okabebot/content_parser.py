"""Conservative local title rules. No network calls or scene-event inference."""

import json
import re
import unicodedata
from pathlib import Path
from .leagues import detect as detect_league


def local_teams():
    path = Path(__file__).parent / "assets/teams.local.json"
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, list) else []
    except (OSError, ValueError):
        return []


TEAMS = local_teams()
SPORT_MARKERS = {
    "soccer": (
        "premier league",
        "la liga",
        "laliga",
        "uefa",
        "champions league",
        "europa league",
        "soccer",
        "mls",
        "major league soccer",
        "bundesliga",
        "serie a",
        "ligue 1",
        "fifa world cup",
    ),
    "american_football": ("nfl", "super bowl", "college football", "ncaa football"),
    "basketball": ("nba", "wnba", "basketball"),
    "baseball": ("mlb", "baseball"),
    "hockey": ("nhl", "ice hockey"),
    "rugby": ("rugby",),
    "cricket": ("cricket",),
    "tennis": ("tennis", "atp", "wta"),
    "golf": ("golf", "pga tour", "lpga"),
    "motorsport": ("formula 1", "formula one", "f1", "nascar", "motogp"),
    "combat": ("ufc", "boxing", "mma"),
}


def words(text):
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def contains(text, phrase):
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))


def resolve_team(side, teams=None):
    text = words(side)
    matches = []
    for team in TEAMS if teams is None else teams:
        # The unqualified Milan alias is ambiguous with Inter Milan.
        if team["key"] == "ac_milan" and contains(text, "inter"):
            continue
        for alias in sorted(team.get("aliases", [team["name"]]), key=len, reverse=True):
            if contains(text, words(alias)):
                matches.append(team)
                break
    return matches[0] if len(matches) == 1 else None


def matchup_names(title):
    segment = str(title).split("|")[0]
    segment = re.sub(r"^(?:live|soccer|nfl|nba|nhl|mlb)\s*[:–-]\s*", "", segment, flags=re.I)
    pair = re.split(r"\s+(?:v\.?|vs\.?|versus|at|@)\s+", segment, maxsplit=1, flags=re.I)
    if len(pair) != 2:
        return []
    pair = [
        re.sub(
            r"\s+(?:extended highlights|highlights|recap|full (?:match|game)(?: highlights)?|live stream|\d{1,2}/\d{1,2}/\d{2,4})\b.*$",
            "",
            p,
            flags=re.I,
        ).strip()
        for p in pair
    ]
    pair = [re.sub(r"\s+\d{1,3}(?:\s*[-–:]\s*\d{1,3})?\s*$", "", p).strip() for p in pair]
    return pair if all(1 <= len(p) <= 60 for p in pair) else []


def parse_video(video, teams=None):
    title = video.get("title") or ""
    result = dict(context={}, source="unknown", evidence=[], unresolved=[])
    fubo = "fubo" in str(video.get("app", "")).casefold()
    if not video.get("app") or not title or str(video["app"]).casefold() == "spotify":
        return result
    text = words(title)
    league = detect_league(text)
    from .video_categories import classify

    generic, generic_evidence = classify(video, text)
    if generic.get("kind") in ("movie", "episode") or generic.get("format") in (
        "game_review",
        "gameplay",
        "esports",
        "film_review",
        "trailer",
        "comedy_sketch",
        "standup",
    ):
        result.update(
            context=generic,
            source="metadata" if generic_evidence.startswith("provider") else "title_rules",
        )
        result["evidence"].append(generic_evidence)
        return result
    # Real clubs appear in game videos too. Don't attach real-match badges.
    if any(
        contains(text, w) for w in ("ea fc", "efootball", "football manager", "madden", "nba 2k")
    ) or re.search(r"\bfifa (?:\d{2}\b|gameplay|career)", text):
        result.update(
            context=dict(kind="video", format="gameplay", confidence=0.85),
            source="title_rules",
            evidence=["video-game marker"],
        )
        return result
    sports = [
        sport
        for sport, markers in SPORT_MARKERS.items()
        if any(contains(text, marker) for marker in markers)
    ]
    if league and league["sport"] not in sports:
        sports.append(league["sport"])
    # Sports context must precede the generic 'highlights' word.
    matchup = matchup_names(title)
    participants = []
    if len(matchup) == 2:
        pair = [resolve_team(side, teams) for side in matchup]
        if all(pair) and pair[0]["key"] != pair[1]["key"] and pair[0]["sport"] == pair[1]["sport"]:
            participants = [
                dict(name=t["name"], short_name=t["short_name"], crest=t["key"], colors=t["colors"])
                for t in pair
            ]
            if not sports:
                sports = [pair[0]["sport"]]
            result["evidence"].append("two identified teams separated by versus")
    competition = (
        len(matchup) == 2
        and not any(
            contains(text, marker)
            for marker in ("movie", "film", "trailer", "debate", "skit", "comedy", "rap battle")
        )
        and (
            fubo
            or any(
                contains(text, marker)
                for marker in ("highlights", "highlight", "recap", "match", "live")
            )
        )
    )
    if competition and not sports:
        sports = ["unknown"]
        result["unresolved"].append("sport awaiting team lookup")
    if not sports and not competition:
        context, evidence = generic, generic_evidence
        if context:
            result.update(
                context=context,
                source="metadata" if evidence.startswith("provider") else "title_rules",
            )
            result["evidence"].append(evidence)
            return result
    if len(sports) != 1:
        result["unresolved"].append("sport missing or ambiguous")
        return result
    sport = sports[0]
    if any(contains(text, w) for w in ("highlights", "highlight", "recap")):
        fmt = "sports_highlights"
        result["evidence"].append("highlight/recap marker")
    elif any(contains(text, w) for w in ("analysis", "breakdown", "tactics", "tactical")):
        fmt = "sports_analysis"
        result["evidence"].append("analysis marker")
    elif (
        contains(text, "live") or video.get("stream_type") == "LIVE" or (fubo and len(matchup) == 2)
    ):
        fmt = "sports_live"
        result["evidence"].append("Fubo matchup title" if fubo else "explicit live marker")
    else:
        if generic:
            result.update(context=generic, source="title_rules")
            result["evidence"].append(generic_evidence)
            return result
        result["unresolved"].append("sports format not explicit")
        return result
    if participants and any(t["sport"] != sport for t in (pair if len(matchup) == 2 else [])):
        participants = []
    if not participants:
        result["unresolved"].append(
            "team identities unverified; showing title labels without crests"
        )
        if len(matchup) == 2:
            participants = [
                dict(
                    name=name,
                    short_name="".join(w[0] for w in name.split())[:5].upper(),
                    crest="",
                    colors=["#486a81", "#ffffff"],
                )
                for name in matchup
            ]
    context = dict(
        kind="video",
        format=fmt,
        sport=sport,
        participants=participants,
        energy=0.5 if fmt == "sports_highlights" else 0.35,
        confidence=0.95
        if "two identified teams separated by versus" in result["evidence"]
        else 0.8,
    )
    if league:
        context["league"] = league["id"]
        result["evidence"].append("league: " + league["name"])
    result.update(context=context, source="title_rules")
    result["evidence"].append("sport: " + sport)
    return result

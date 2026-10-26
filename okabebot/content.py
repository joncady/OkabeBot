"""Parser-independent content slots and character reaction plans."""

import json
import math
import os
import re
import tempfile
import time
from pathlib import Path

PRESETS = json.loads((Path(__file__).parent / "assets/content-presets.json").read_text())
BY_ID = {p["id"]: p for p in PRESETS}
REACTIONS = (
    "attentive",
    "engaged",
    "amused",
    "tense",
    "wonder",
    "curious",
    "moved",
    "delighted",
    "upbeat",
    "calm",
    "competitive",
    "analytical",
    "energetic",
    "serious",
)
SPORTS = (
    "unknown",
    "soccer",
    "american_football",
    "basketball",
    "baseball",
    "hockey",
    "tennis",
    "golf",
    "motorsport",
    "combat",
    "rugby",
    "cricket",
)


def normalize(context):
    if not isinstance(context, dict):
        raise ValueError("context must be an object")
    kind = context.get("kind", "unknown")
    if kind not in ("unknown", "movie", "episode", "video", "music"):
        raise ValueError("Unknown content kind")
    genres = context.get("genres", [])
    if (
        not isinstance(genres, list)
        or len(genres) > 5
        or any(not isinstance(g, str) or "movie." + g not in BY_ID for g in genres)
    ):
        raise ValueError("Use up to five movie genre keys from the catalog")
    fmt = context.get("format", "")
    if fmt and "video." + str(fmt) not in BY_ID:
        raise ValueError("Unknown video format")
    reaction = context.get("reaction")
    if reaction is not None and reaction not in REACTIONS:
        raise ValueError("Unknown reaction")
    sport = context.get("sport", "unknown")
    if sport not in SPORTS:
        raise ValueError("Unknown sport")
    confidence = context.get("confidence", 1)
    energy = context.get("energy", 0.4)
    for value in (confidence, energy):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("confidence and energy must be 0..1")
    teams = context.get("participants", [])
    if not isinstance(teams, list) or len(teams) > 2:
        raise ValueError("Use at most two participants")
    participants = []
    for team in teams:
        if not isinstance(team, dict):
            raise ValueError("Participant must be an object")
        label, short = team.get("name", ""), team.get("short_name", "")
        if not isinstance(label, str) or not 1 <= len(label) <= 60:
            raise ValueError("Participant name required, max 60 characters")
        if not isinstance(short, str) or len(short) > 5:
            raise ValueError("Participant short_name max five characters")
        colors = team.get("colors", ["#486a81", "#ffffff"])
        if (
            not isinstance(colors, list)
            or len(colors) != 2
            or any(
                not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors
            )
        ):
            raise ValueError("Participant colors require two hex colors")
        crest = team.get("crest", "")
        if not isinstance(crest, str) or not re.fullmatch(r"[a-z0-9_-]{0,64}", crest):
            raise ValueError("crest must be a local asset key")
        participants.append(
            dict(name=label, short_name=short or label[:3].upper(), colors=colors, crest=crest)
        )
    return dict(
        kind=kind,
        genres=genres,
        format=fmt,
        sport=sport,
        confidence=confidence,
        energy=energy,
        reaction=reaction,
        participants=participants,
        league=str(context.get("league", ""))[:80],
    )


def plan(context):
    c = normalize(context)
    key = (
        "movie." + c["genres"][0]
        if c["kind"] in ("movie", "episode") and c["genres"]
        else "video." + (c["format"] or "unknown")
    )
    preset = BY_ID.get(key, BY_ID["video.unknown"])
    known = c["confidence"] >= 0.7
    return dict(
        preset=key,
        reaction=(c["reaction"] or preset["reaction"]) if known else "attentive",
        prop=preset["prop"]
        if known and not (c["sport"] == "unknown" and str(c["format"]).startswith("sports_"))
        else "screen",
        energy=c["energy"] if known else 0.2,
        sport=c["sport"] if known else "unknown",
        participants=c["participants"] if known else [],
        confidence=c["confidence"],
        league=c["league"],
    )


class ContentContext:
    """Explicit context is scoped to one app/content ID, never leaks to next video."""

    def __init__(self, folder):
        self.path = Path(folder) / "content-context.json"

    def set(self, app, content_id, context):
        if not all(isinstance(x, str) and 0 < len(x) <= 500 for x in (app, content_id)):
            raise ValueError("Verified app and content_id required")
        value = dict(
            app=app,
            content_id=content_id,
            context=normalize(context),
            expires_at=time.time() + 14400,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(value, f)
            tmp = Path(f.name)
        tmp.replace(self.path)
        return dict(value, plan=plan(value["context"]))

    def get(self, video, fallback=None):
        try:
            v = json.loads(self.path.read_text())
            if (
                v["app"] == video.get("app")
                and v["content_id"] == video.get("content_id")
                and v["expires_at"] > time.time()
            ):
                return plan(v["context"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        from .content_parser import parse_video

        return plan(parse_video(video)["context"] if fallback is None else fallback)


class ContentPreview:
    """A bounded manual demo, independent of TV apps and content identities."""

    def __init__(self):
        self.value = None
        self.until = 0

    def start(self, context):
        reaction = plan(context)
        preset = BY_ID.get(reaction["preset"], BY_ID["video.unknown"])
        self.value = dict(
            is_playing=False,
            preview_seconds=95,
            video=dict(
                app="Preview",
                title="Reaction preview · " + preset["label"],
                state="PLAYING",
                reaction=reaction,
            ),
        )
        self.until = time.monotonic() + 90
        return dict(preview=True, seconds=90, plan=reaction)

    def stop(self):
        self.value = None
        self.until = 0

    def music(self):
        if self.value is not None and time.monotonic() < self.until:
            return self.value
        return None

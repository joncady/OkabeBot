"""Auditable format rules and provider metadata normalization, without title catalogs."""

import re

GENRES = {
    "sci fi": "science_fiction",
    "science fiction": "science_fiction",
    "romantic comedy": "romance",
    "animated": "animation",
}
FORMATS = (
    ("science", r"\b(?:science experiment|physics explained|chemistry explained)\b"),
    ("nonprofit", r"\b(?:charity fundraiser|nonprofit campaign)\b"),
    ("shorts", r"\bshorts\b"),
    ("game_review", r"\b(?:game review|review of .* game|gaming review)\b"),
    ("film_review", r"\b(?:movie review|film review|cinema review)\b"),
    ("technology_review", r"\b(?:tech review|technology review|smartphone review|laptop review)\b"),
    ("trailer", r"\b(?:official trailer|teaser trailer|movie trailer)\b"),
    ("standup", r"\bstand up (?:comedy|special)\b"),
    ("comedy_sketch", r"\b(?:comedy skit|comedy sketch|comedy sketches|sketch comedy)\b"),
    ("esports", r"\b(?:esports|e sports)\b"),
    ("gameplay", r"\b(?:gameplay|walkthrough|speedrun|lets play)\b"),
    ("music_video", r"\b(?:official music video|official lyric video)\b"),
    ("concert", r"\b(?:full concert|live concert)\b"),
    ("podcast", r"\bpodcast\b"),
    ("interview", r"\binterview\b"),
    ("news", r"\b(?:breaking news|news bulletin|news update)\b"),
    ("asmr", r"\basmr\b"),
    ("relaxation", r"\b(?:sleep meditation|guided meditation|relaxing sounds)\b"),
    ("fitness", r"\b(?:workout|fitness routine|yoga session)\b"),
    ("food", r"\b(?:recipe|cooking tutorial|baking tutorial)\b"),
    ("diy", r"\b(?:diy|woodworking|home repair)\b"),
    ("automotive", r"\b(?:car review|test drive|auto review)\b"),
    ("fashion", r"\b(?:fashion show|makeup tutorial|outfit ideas)\b"),
    ("nature", r"\b(?:wildlife documentary|nature documentary)\b"),
    ("animals", r"\b(?:animal rescue|cute cats|cute dogs)\b"),
    ("travel", r"\b(?:travel guide|travel vlog|walking tour)\b"),
    ("vlog", r"\bvlog\b"),
    ("lecture", r"\b(?:lecture|university course)\b"),
    ("tutorial", r"\b(?:tutorial|how to)\b"),
    ("reaction", r"\b(?:reaction video|reacts to)\b"),
)


def classify(video, text):
    from .content import BY_ID

    metadata = video.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    kind = metadata.get("kind")
    if kind in ("movie", "episode"):
        genres = metadata.get("genres", [])
        if isinstance(genres, str):
            genres = re.split("[,;/]", genres)
        clean = []
        for value in genres if isinstance(genres, list) else []:
            if not isinstance(value, str):
                continue
            value = re.sub(r"[^\w]+", " ", value.casefold()).strip()
            key = GENRES.get(value, value.replace(" ", "_"))
            if "movie." + key in BY_ID and key not in clean:
                clean.append(key)
        if clean:
            return dict(kind=kind, genres=clean[:5], confidence=0.95), "provider genre metadata"
    for fmt, pattern in FORMATS:
        if re.search(pattern, text):
            return dict(kind="video", format=fmt, confidence=0.85), "title format: " + fmt
    # Explicit genre + film marker is evidence; arbitrary words inside movie names are not.
    for key in [p.removeprefix("movie.") for p in BY_ID if p.startswith("movie.")]:
        genre = key.replace("_", " ")
        if re.search(r"\b" + genre + r" (?:movie|film|documentary)\b", text):
            return dict(kind="movie", genres=[key], confidence=0.8), "explicit genre marker"
    return {}, ""

"""Cached on-demand Wikipedia/Wikidata team resolution. No manual team list required."""

import base64
import hashlib
import io
import json
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlencode, unquote, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from functools import lru_cache

from PIL import Image
from .content_parser import parse_video, matchup_names, words
from .leagues import matches as league_matches

SPORT_NAMES = {
    "association football": "soccer",
    "american football": "american_football",
    "basketball": "basketball",
    "baseball": "baseball",
    "ice hockey": "hockey",
    "rugby union": "rugby",
    "rugby league": "rugby",
    "cricket": "cricket",
    "tennis": "tennis",
    "volleyball": None,
}


_FETCH_LOCK = threading.Lock()
_FETCH_NEXT = 0
_FETCH_BACKOFF = 0


@lru_cache(maxsize=512)
def wiki_get(url, raw=False):
    host = urlsplit(url).hostname or ""
    if host not in (
        "en.wikipedia.org",
        "www.wikidata.org",
        "upload.wikimedia.org",
        "thumb.wikimedia.org",
    ):
        raise ValueError("Unsupported metadata host")
    request = Request(
        url,
        headers={
            "User-Agent": "OkabeBot/0.1 (https://github.com/joncady/OkabeBot; cached personal companion)"
        },
    )
    global _FETCH_NEXT, _FETCH_BACKOFF
    with _FETCH_LOCK:
        if time.monotonic() < _FETCH_BACKOFF:
            raise OSError("Wikimedia request backoff active")
        time.sleep(max(0, _FETCH_NEXT - time.monotonic()))
        _FETCH_NEXT = time.monotonic() + 1.1
        try:
            with urlopen(request, timeout=8) as r:
                data = r.read(2_000_001)
        except HTTPError as exc:
            if exc.code == 429:
                try:
                    retry = max(120, int(exc.headers.get("Retry-After", "120")))
                except ValueError:
                    retry = 120
                _FETCH_BACKOFF = time.monotonic() + retry
            raise
    if len(data) > 2_000_000:
        raise ValueError("Metadata response too large")
    return data if raw else json.loads(data)


def team_tokens(name):
    return set(words(name).split()) - {
        "fc",
        "cf",
        "afc",
        "a",
        "f",
        "c",
        "club",
        "football",
        "the",
    }


class TeamResolver:
    def __init__(self, folder, upload=None, fetch=wiki_get):
        self.path = Path(folder) / "sports-resolver.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS teams (key TEXT PRIMARY KEY, value TEXT, expires REAL)"
            )
            c.execute(
                "CREATE TABLE IF NOT EXISTS crest_assets (qid TEXT PRIMARY KEY, value TEXT, expires REAL, error TEXT)"
            )
            # Old negative results may have included temporary provider failures.
            if c.execute("PRAGMA user_version").fetchone()[0] < 3:
                c.execute("DELETE FROM teams WHERE value='null'")
                c.execute("PRAGMA user_version=3")
        self.fetch = fetch
        self.upload = upload
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sports-resolver")
        self.lock = threading.Lock()
        self.future = None
        self.results = {}
        self.crest_attempts = {}

    def db(self):
        return sqlite3.connect(self.path, timeout=5)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    def entity(self, qid):
        data = self.fetch("https://www.wikidata.org/wiki/Special:EntityData/" + qid + ".json")
        return data["entities"][qid]

    def candidate(self, name, title, sport, league=""):
        summary = self.fetch(
            "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"))
        )
        if summary.get("type") == "disambiguation" or not summary.get("wikibase_item"):
            return None
        qid = summary["wikibase_item"]
        if not re.fullmatch(r"Q\d+", qid):
            return None
        actual = summary["title"]
        query = team_tokens(name)
        canonical = team_tokens(actual)
        if not query or not query.issubset(canonical):
            return None
        # Do not silently select a women's/youth side for an unqualified club name.
        if any(
            set(token.split()).issubset(set(words(actual).split()))
            and not set(token.split()).issubset(set(words(name).split()))
            for token in (
                "women",
                "youth",
                "under 21",
                "under 23",
                "ii",
                "iii",
                "reserves",
                "academy",
            )
        ):
            return None
        entity = self.entity(qid)
        claims = entity.get("claims", {})
        labels_by_property = {}
        ids_by_property = {}
        for prop in ("P641", "P31", "P118"):
            ids_by_property[prop] = [
                claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                for claim in claims.get(prop, [])
                if isinstance(claim.get("mainsnak", {}).get("datavalue", {}).get("value"), dict)
            ][:6]
        ids = list(dict.fromkeys(i for values in ids_by_property.values() for i in values if i))
        entities = {}
        if ids:
            entities = self.fetch(
                "https://www.wikidata.org/w/api.php?"
                + urlencode(
                    dict(
                        action="wbgetentities",
                        ids="|".join(ids),
                        props="labels",
                        languages="en",
                        format="json",
                    )
                )
            ).get("entities", {})
        for prop, values in ids_by_property.items():
            labels_by_property[prop] = [
                entities.get(i, {}).get("labels", {}).get("en", {}).get("value", "")
                for i in values
                if i
            ]
        labels = labels_by_property["P641"] + labels_by_property["P31"]
        claimed_sports = labels_by_property["P641"]
        claimed_leagues = labels_by_property["P118"]
        if league and claimed_leagues and not league_matches(league, claimed_leagues):
            return None
        if any("season" in label.casefold() for label in labels_by_property["P31"]):
            return None
        resolved = {
            value
            for label, value in SPORT_NAMES.items()
            if value and any(label in text.casefold() for text in labels)
        }
        typed_sports = {
            value
            for label, value in SPORT_NAMES.items()
            if value and any(label in text.casefold() for text in labels_by_property["P31"])
        }
        # A specific 'ice hockey team' type is stronger than inconsistent P641
        # entries on the same entity; a generic club type cannot resolve a conflict.
        if len(typed_sports) == 1:
            resolved = typed_sports
        # P641/P31 must establish an unambiguous sport; summary images alone are not proof.
        if len(resolved) > 1 or (not resolved and len(claimed_sports) != 1):
            return None
        actual_sport = resolved.pop() if resolved else "unknown"
        if sport and actual_sport != sport:
            return None
        if not any(t in " ".join(labels).casefold() for t in ("team", "club", "franchise")):
            return None
        score = 1 if query == canonical else len(query) / len(canonical)
        result = dict(
            name=actual,
            short_name="".join(w[0] for w in actual.split()[:4]).upper(),
            sport=actual_sport,
            sport_label=claimed_sports[0] if claimed_sports else actual_sport,
            crest="wiki_" + qid.lower(),
            key="wiki_" + qid.lower(),
            qid=qid,
            aliases=[actual, name],
            source="https://en.wikipedia.org/wiki/" + quote(actual.replace(" ", "_")),
            colors=["#486a81", "#ffffff"],
            score=score,
            leagues=claimed_leagues,
            league=league if league_matches(league, claimed_leagues) else "",
        )
        result["asset_hint"] = self.crest_hint(summary)
        return result

    @staticmethod
    def crest_hint(summary):
        image = summary.get("thumbnail", {}).get("source", "").split("?")[0]
        file_title = unquote(image.split("/")[-2]) if "/thumb/" in image else ""
        # A verified club's lead SVG is usable even when its filename is a
        # compressed name (e.g. no whitespace). Raster photos remain excluded.
        if image and (
            file_title.casefold().endswith(".svg")
            or any(x in file_title.casefold() for x in ("logo", "crest", "badge"))
        ):
            return {"image_url": image, "file_title": file_title}
        return {}

    def ensure_crest(self, team):
        if team.get("png_base64"):
            return team, None, None
        cached = self.crest_attempts.get(team["qid"])
        if cached and cached[1] > time.time():
            return cached
        with self.db() as db:
            row = db.execute(
                "SELECT value,expires,error FROM crest_assets WHERE qid=? AND expires>?",
                (team["qid"], time.time()),
            ).fetchone()
        if row:
            entry = (dict(team, **json.loads(row[0])), row[1], row[2])
            self.crest_attempts[team["qid"]] = entry
            return entry
        result = dict(team)
        try:
            hint = team.get("asset_hint")
            if hint is None:
                summary = self.fetch(
                    "https://en.wikipedia.org/api/rest_v1/page/summary/"
                    + quote(team["name"].replace(" ", "_"))
                )
                hint = self.crest_hint(summary)
            if not hint:
                entry = (result, time.time() + 21600, None)
            else:
                image, file_title = hint["image_url"], hint["file_title"]
                raw = self.fetch(image, raw=True)
                with Image.open(io.BytesIO(raw)) as im:
                    im = im.convert("RGBA")
                    im.thumbnail((64, 64), Image.Resampling.NEAREST)
                    buf = io.BytesIO()
                    im.save(buf, format="PNG")
                result["png_base64"] = base64.b64encode(buf.getvalue()).decode()
                result["asset_source"] = dict(
                    file_page="https://en.wikipedia.org/wiki/File:" + quote(file_title),
                    image_url=image,
                    rights={},
                )
                try:
                    meta = self.fetch(
                        "https://en.wikipedia.org/w/api.php?"
                        + urlencode(
                            dict(
                                action="query",
                                titles="File:" + file_title,
                                prop="imageinfo",
                                iiprop="extmetadata",
                                format="json",
                            )
                        )
                    )
                    page = next(iter(meta.get("query", {}).get("pages", {}).values()), {})
                    ext = page.get("imageinfo", [{}])[0].get("extmetadata", {})
                    result["asset_source"]["rights"] = {
                        k: v.get("value")
                        for k, v in ext.items()
                        if k in ("LicenseShortName", "UsageTerms", "Artist", "Copyrighted")
                    }
                except (OSError, ValueError, KeyError):
                    pass
                entry = (result, time.time() + 2592000, None)
        except (OSError, ValueError, KeyError):
            entry = (
                result,
                time.time() + max(120, _FETCH_BACKOFF - time.monotonic()),
                "Team crest unavailable; retrying",
            )
        if len(self.crest_attempts) >= 100:
            self.crest_attempts.clear()
        self.crest_attempts[team["qid"]] = entry
        assets = {
            k: v for k, v in entry[0].items() if k in ("png_base64", "asset_source", "asset_hint")
        }
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO crest_assets VALUES (?,?,?,?)",
                (team["qid"], json.dumps(assets), entry[1], entry[2]),
            )
        return entry

    def resolve(self, name, sport=None, league=""):
        key = words(name) + "|" + (sport or "") + ("|" + league if league else "")
        with self.db() as c:
            row = c.execute(
                "SELECT value FROM teams WHERE key=? AND expires>?", (key, time.time())
            ).fetchone()
        if row and json.loads(row[0]) is not None:
            return json.loads(row[0])
        # A previously validated identity can serve a new league hint (or no hint).
        with self.db() as c:
            rows = c.execute(
                "SELECT value FROM teams WHERE substr(key,1,instr(key,'|')-1)=? AND expires>?",
                (words(name), time.time()),
            ).fetchall()
        candidates = [json.loads(row[0]) for row in rows]
        candidates = [
            t
            for t in candidates
            if t
            and (not sport or t["sport"] == sport)
            and (league_matches(league, t.get("leagues", [])) if league else not t.get("league"))
        ]
        if len({t["qid"] for t in candidates}) == 1:
            return candidates[0]
        if row:
            return None
        try:
            exact = (
                self.candidate(name, name, sport, league)
                if league
                else self.candidate(name, name, sport)
            )
        except HTTPError as exc:
            if exc.code != 404:
                raise
            exact = None
        if exact and words(exact["name"]) == words(name):
            with self.db() as c:
                c.execute(
                    "INSERT OR REPLACE INTO teams VALUES (?,?,?)",
                    (key, json.dumps(exact), time.time() + 2592000),
                )
            return exact
        search = self.fetch(
            "https://en.wikipedia.org/w/api.php?"
            + urlencode(
                dict(
                    action="query",
                    list="search",
                    srsearch=name
                    + " "
                    + (
                        {"soccer": "football club", "american_football": "NFL team"}.get(
                            sport, sport or "sports team"
                        )
                    ),
                    srlimit=4,
                    format="json",
                )
            )
        )
        matches = []
        transient = False
        for hit in search.get("query", {}).get("search", []):
            try:
                value = (
                    self.candidate(name, hit["title"], sport, league)
                    if league
                    else self.candidate(name, hit["title"], sport)
                )
                if value:
                    matches.append(value)
                    # An exact full canonical name is authoritative; an overlap
                    # score alone is not enough to stop checking alternatives.
                    if words(value.get("name", "")) == words(name):
                        break
            except HTTPError as exc:
                if exc.code != 404:
                    transient = True
                continue
            except OSError:
                transient = True
                continue
            except (ValueError, KeyError):
                continue
        if transient:
            raise OSError("Team metadata temporarily unavailable")
        matches = list({m["qid"]: m for m in matches}.values())
        matches.sort(key=lambda x: x["score"], reverse=True)
        result = (
            matches[0]
            if matches and (len(matches) == 1 or matches[0]["score"] - matches[1]["score"] >= 0.2)
            else None
        )
        with self.db() as c:
            c.execute(
                "INSERT OR REPLACE INTO teams VALUES (?,?,?)",
                (key, json.dumps(result), time.time() + (2592000 if result else 300)),
            )
        return result

    def _enrich(self, video):
        basic = parse_video(video)
        names = matchup_names(video.get("title", ""))
        if len(names) != 2:
            return basic
        hint = basic.get("context", {}).get("sport")
        if hint == "unknown":
            hint = None
        league = basic.get("context", {}).get("league", "")
        pair = [self.resolve(n, hint, league) if league else self.resolve(n, hint) for n in names]
        if (
            not all(pair)
            or pair[0]["qid"] == pair[1]["qid"]
            or pair[0]["sport"] != pair[1]["sport"]
            or (
                pair[0]["sport"] == "unknown"
                and pair[0].get("sport_label") != pair[1].get("sport_label")
            )
        ):
            basic["unresolved"].append("dynamic team resolution abstained")
            basic["retry_at"] = time.time() + 300
            return basic
        enriched = parse_video(video, teams=pair)
        context = enriched.get("context", {})
        for p, t in zip(context.get("participants", []), pair):
            t, retry_at, error = self.ensure_crest(t)
            if retry_at and not t.get("png_base64"):
                enriched["retry_at"] = min(enriched.get("retry_at", retry_at), retry_at)
            if error:
                enriched["lookup_error"] = error
            p["crest"] = ""
            if t.get("png_base64") and self.upload:
                try:
                    reply = self.upload(
                        {"op": "cache_crest", "key": t["crest"], "png_base64": t["png_base64"]}
                    )
                    if not reply.get("error"):
                        p["crest"] = t["crest"]
                except (OSError, RuntimeError):
                    pass
                if not p["crest"]:
                    enriched["lookup_error"] = "Crest delivery unavailable; retrying"
                    enriched["retry_at"] = time.time() + 30
        enriched["source"] = "title_rules+wikidata"
        enriched["evidence"].extend(t["source"] for t in pair)
        return enriched

    def get(self, video):
        basic = parse_video(video)
        names = matchup_names(video.get("title", ""))
        if len(names) != 2 or not is_supported(video):
            return basic
        if not str(basic.get("context", {}).get("format", "")).startswith("sports_"):
            return basic
        key = hashlib.sha256(
            json.dumps([video.get("app"), video.get("title"), video.get("content_id")]).encode()
        ).hexdigest()
        with self.lock:
            if key in self.results:
                cached = self.results[key]
                if cached.get("retry_at") and cached["retry_at"] < time.time():
                    del self.results[key]
                else:
                    return cached
            if self.future is None or self.future.done():
                self.future = self.pool.submit(self._run, key, dict(video))
        return dict(basic, resolving=True)

    def _run(self, key, video):
        try:
            result = self._enrich(video)
        except Exception as exc:
            limited = (
                isinstance(exc, HTTPError) and exc.code == 429
            ) or time.monotonic() < _FETCH_BACKOFF
            result = dict(
                parse_video(video),
                lookup_error="Wikipedia rate limited; showing title labels"
                if limited
                else "Team lookup unavailable; showing title labels",
                retry_at=time.time() + max(120, _FETCH_BACKOFF - time.monotonic()),
            )
        with self.lock:
            if len(self.results) > 100:
                self.results.clear()
            self.results[key] = result


def is_supported(video):
    app = str(video.get("app", "")).casefold()
    return bool(app and video.get("title")) and app != "spotify"

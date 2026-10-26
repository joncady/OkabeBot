"""Optional cached, asynchronous Wikidata movie/series genre enrichment.

Only exact English labels/aliases with verified work types are accepted. No plot
text, scene timing, or spoilers are fetched or supplied to the character.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.parse import urlencode

from .content_parser import words
from .team_resolver import wiki_get
from .video_categories import GENRES
from .content import BY_ID


class MovieMetadata:
    def __init__(self, folder, fetch=wiki_get):
        self.path = Path(folder) / "movie-metadata.sqlite3"
        with self.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS movies (key TEXT PRIMARY KEY,value TEXT,expires REAL)"
            )
        self.fetch = fetch
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="movie-metadata")
        self.lock = threading.Lock()
        self.future = None
        self.results = {}

    def db(self):
        return sqlite3.connect(self.path, timeout=5)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    def lookup(self, video):
        title = re.sub(r"\s*\((?:19|20)\d{2}\)\s*$", "", video["title"]).strip()
        year = re.search(r"\(((?:19|20)\d{2})\)\s*$", video["title"])
        search = self.fetch(
            "https://www.wikidata.org/w/api.php?"
            + urlencode(
                dict(action="wbsearchentities", search=title, language="en", limit=5, format="json")
            )
        )
        matches = []
        for hit in search.get("search", []):
            qid = hit.get("id", "")
            if not re.fullmatch(r"Q\d+", qid):
                continue
            entity = self.fetch(
                "https://www.wikidata.org/wiki/Special:EntityData/" + qid + ".json"
            )["entities"][qid]
            aliases = [entity.get("labels", {}).get("en", {}).get("value", "")]
            aliases.extend(a["value"] for a in entity.get("aliases", {}).get("en", []))
            if words(title) not in {words(a) for a in aliases}:
                continue
            claims = entity.get("claims", {})
            if year and not any(
                year[1]
                == str(c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("time", ""))[
                    1:5
                ]
                for c in claims.get("P577", [])
            ):
                continue
            ids = {}
            for prop in ("P31", "P136"):
                ids[prop] = [
                    c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                    for c in claims.get(prop, [])
                ][:12]
            qids = list(dict.fromkeys(q for values in ids.values() for q in values if q))
            if not qids:
                continue
            labels = self.fetch(
                "https://www.wikidata.org/w/api.php?"
                + urlencode(
                    dict(
                        action="wbgetentities",
                        ids="|".join(qids),
                        props="labels",
                        languages="en",
                        format="json",
                    )
                )
            ).get("entities", {})

            def label(q):
                return labels.get(q, {}).get("labels", {}).get("en", {}).get("value", "").casefold()

            types = [label(q) for q in ids["P31"]]
            if not any(
                re.search(r"\b(?:film|television series|television episode)\b", t) for t in types
            ):
                continue
            genres = []
            for q in ids["P136"]:
                genre = re.sub(r"\s+(?:film|films|television series)$", "", label(q))
                genre = words(genre)
                key = GENRES.get(genre, genre.replace(" ", "_"))
                if "movie." + key in BY_ID and key not in genres:
                    genres.append(key)
            if genres:
                matches.append(
                    dict(
                        context=dict(
                            kind="episode" if any("television" in t for t in types) else "movie",
                            genres=genres[:5],
                            confidence=0.95,
                        ),
                        source="wikidata",
                        evidence=["https://www.wikidata.org/wiki/" + qid],
                        unresolved=[],
                    )
                )
        return matches[0] if len(matches) == 1 else None

    def _run(self, key, video):
        try:
            result = self.lookup(video)
            expires = time.time() + (30 * 86400 if result else 300)
            with self.db() as db:
                db.execute(
                    "INSERT OR REPLACE INTO movies VALUES (?,?,?)",
                    (key, json.dumps(result), expires),
                )
        except Exception:
            result = None
            expires = time.time() + 120
        with self.lock:
            if len(self.results) >= 100:
                self.results.clear()
            self.results[key] = (result, expires)

    def get(self, video, basic):
        if basic.get("context") or not video.get("title") or video["title"] == "Title unavailable":
            return basic
        app = words(str(video.get("app", "")))
        metadata = video.get("metadata")
        kind = metadata.get("kind") if isinstance(metadata, dict) else None
        if kind not in ("movie", "episode") and app not in (
            "netflix",
            "prime video",
            "amazon prime video",
            "max",
            "hbo max",
            "disney",
            "disney plus",
            "apple tv",
            "hulu",
        ):
            return basic
        key = hashlib.sha256(
            json.dumps([video.get("app"), video["title"], kind]).encode()
        ).hexdigest()
        with self.lock:
            cached = self.results.get(key)
            if cached and cached[1] > time.time():
                return cached[0] or basic
            with self.db() as db:
                row = db.execute(
                    "SELECT value,expires FROM movies WHERE key=? AND expires>?", (key, time.time())
                ).fetchone()
            if row:
                self.results[key] = (json.loads(row[0]), row[1])
                return json.loads(row[0]) or basic
            if self.future is None or self.future.done():
                self.future = self.pool.submit(self._run, key, dict(video))
        return dict(basic, resolving=True)

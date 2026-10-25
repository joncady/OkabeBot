#!/usr/bin/env python3
"""Fetch registered club crests from Wikipedia, retaining file provenance/rights."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode, quote, unquote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TEAMS = json.loads((ROOT / "okabebot/assets/teams.local.json").read_text())
HEADERS = {"User-Agent": "OkabeBot/0.1 (personal hardware display; Wikipedia crest cache)"}


def get(url):
    with urlopen(Request(url, headers=HEADERS), timeout=20) as response:
        return response.read()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("keys", nargs="*", help="Registered team keys; default is all")
args = parser.parse_args()
unknown = set(args.keys) - {t["key"] for t in TEAMS}
if unknown:
    sys.exit("Unknown team keys: " + ", ".join(sorted(unknown)))
folder = ROOT / "pi/assets/crests"
folder.mkdir(parents=True, exist_ok=True)
sources = (
    json.loads((folder / "sources.json").read_text()) if (folder / "sources.json").exists() else []
)
for team in TEAMS:
    if args.keys and team["key"] not in args.keys:
        continue
    summary = json.loads(
        get("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(team["wikipedia"]))
    )
    image_url = summary["thumbnail"]["source"].split("?")[0]
    # API image is a Wikimedia-hosted thumbnail; use it without generating artwork.
    if not image_url.startswith(("https://upload.wikimedia.org/", "https://thumb.wikimedia.org/")):
        sys.exit("Unexpected image host")
    file_title = unquote(image_url.split("/")[-2])
    info = json.loads(
        get(
            "https://en.wikipedia.org/w/api.php?"
            + urlencode(
                dict(
                    action="query",
                    titles="File:" + file_title,
                    prop="imageinfo",
                    iiprop="url|extmetadata",
                    format="json",
                )
            )
        )
    )
    details = next(iter(info["query"]["pages"].values())).get("imageinfo", [{}])[0]
    rights = {
        k: v.get("value")
        for k, v in details.get("extmetadata", {}).items()
        if k in ["LicenseShortName", "UsageTerms", "Attribution", "Artist", "Copyrighted"]
    }
    (folder / (team["key"] + ".png")).write_bytes(get(image_url))
    source = dict(
        key=team["key"],
        name=team["name"],
        page="https://en.wikipedia.org/wiki/" + team["wikipedia"],
        file_page="https://en.wikipedia.org/wiki/File:" + quote(file_title),
        image_url=image_url,
        rights=rights,
    )
    sources = [r for r in sources if r["key"] != team["key"]] + [source]
    (folder / "sources.json").write_text(json.dumps(sources, indent=2) + "\n")
    print(team["key"] + ": cached")
(ROOT / "okabebot/assets/crests.local.json").write_text(
    json.dumps(
        [
            dict(key=t["key"], name=t["name"])
            for t in TEAMS
            if (folder / (t["key"] + ".png")).exists()
        ],
        indent=2,
    )
    + "\n"
)

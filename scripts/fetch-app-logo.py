#!/usr/bin/env python3
"""Cache a Wikipedia File logo with attribution; no downloads in the renderer."""

import argparse
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from okabebot.team_resolver import wiki_get

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("key", help="App icon key from media-apps.json")
parser.add_argument("file", help="Exact Wikipedia File: title, selected from its app article")
args = parser.parse_args()
if not args.key.isalnum() or not args.file.startswith("File:"):
    parser.error("Use an alphanumeric icon key and a File: title")
result = wiki_get(
    "https://en.wikipedia.org/w/api.php?"
    + urlencode(
        dict(
            action="query",
            titles=args.file,
            prop="imageinfo",
            iiprop="url|extmetadata",
            iiurlwidth=64,
            format="json",
        )
    )
)
page = next(iter(result["query"]["pages"].values()))
info = page["imageinfo"][0]
raw = wiki_get(info.get("thumburl") or info["url"], raw=True)
with Image.open(io.BytesIO(raw)) as im:
    im = im.convert("RGBA")
    im.thumbnail((64, 64))
    folder = Path(__file__).resolve().parents[1] / "pi/assets/app-logos"
    folder.mkdir(parents=True, exist_ok=True)
    im.save(folder / (args.key + ".png"))
(folder / (args.key + ".json")).write_text(
    json.dumps(
        dict(
            file=args.file, file_page=info.get("descriptionurl"), rights=info.get("extmetadata", {})
        ),
        indent=2,
    )
)
print(
    "Cached",
    args.key,
    "with source and rights metadata; copy the app-logos directory to your display Pi.",
)

#!/usr/bin/env python3
"""Render a contact sheet for every content preset; no live hardware changes."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from okabebot.content import PRESETS, plan
from pi import scene

parser = argparse.ArgumentParser()
parser.add_argument("--output", default=".local/content-reactions.png")
parser.add_argument("--character", default="kurisu", choices=["kurisu", "okabe", "sonic", "pip"])
args = parser.parse_args()
cols = 5
sheet = Image.new("RGB", (cols * 240, ((len(PRESETS) + cols - 1) // cols) * 180), "#101e25")
for i, preset in enumerate(PRESETS):
    kind, key = preset["id"].split(".")
    c = {
        "kind": kind,
        "genres": [key] if kind == "movie" else [],
        "format": key if kind == "video" else "",
    }
    if key.startswith("sports"):
        c.update(
            sport="soccer",
            participants=[
                {"name": "Home", "short_name": "HOM"},
                {"name": "Away", "short_name": "AWY"},
            ],
        )
    video = {"app": "YouTube", "title": preset["label"], "state": "PLAYING", "reaction": plan(c)}
    im = scene.render(style=args.character, music={"video": video}, phase=2).resize((240, 160))
    x, y = (i % cols) * 240, (i // cols) * 180
    sheet.paste(im, (x, y))
    ImageDraw.Draw(sheet).text((x + 6, y + 162), preset["id"], fill="#ffffff")
p = Path(args.output)
p.parent.mkdir(parents=True, exist_ok=True)
sheet.save(p)
print(str(p.resolve()))

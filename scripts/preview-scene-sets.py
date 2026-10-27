#!/usr/bin/env python3
"""Export a generic scene gallery without hardware, state changes or live data."""

import argparse
import html
from pathlib import Path
import subprocess
import sys

from okabebot.scene_sets import CATALOG


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local/scene-sets-preview"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cards = []
    for character, choices in CATALOG["characters"].items():
        for scene in choices:
            folder = args.output / (character + "-" + scene)
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("build-alexa-character.py")),
                    "--character",
                    character,
                    "--set",
                    scene,
                    "--output",
                    str(folder),
                ],
                check=True,
            )
            label = html.escape(character.title() + " · " + CATALOG["sets"][scene]["name"])
            cards.append(
                f'<article><h2>{label}</h2><div class="views"><figure><img src="{folder.name}/idle.png" alt="{label} room"><figcaption>Room</figcaption></figure><figure><img class="small" src="{folder.name}/companion.png" alt="{label} companion"><figcaption>Companion</figcaption></figure></div></article>'
            )
    (args.output / "index.html").write_text(
        """<!doctype html><meta charset="utf-8"><title>Little Lab · Scene sets</title><style>body{background:#101b27;color:#e4eadb;font:16px monospace;margin:32px}h1{color:#aed6c2}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(540px,1fr));gap:24px}article{background:#1b303b;border:2px solid #48666b;padding:12px}h2{font-size:18px}.views{display:grid;grid-template-columns:3fr 1fr;gap:8px}figure{margin:0;align-self:center}img{width:100%;image-rendering:pixelated}.small{background:repeating-conic-gradient(#152630 0% 25%,#1e333b 0% 50%) 0/16px 16px}figcaption{padding:8px;color:#a0c1b4}p{max-width:900px;line-height:1.5}</style><h1>Little Lab · Two sets per character</h1><p>Room and Companion are two views of the same set. A set can be assigned to one physical location per character, regardless of view. This is generic artwork for review, not live device state.</p><main>"""
        + "".join(cards)
        + "</main>"
    )
    print(args.output / "index.html")


if __name__ == "__main__":
    main()

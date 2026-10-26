#!/usr/bin/env python3
"""Generate README integration examples without touching connected devices."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from pi import scene

cases = [
    (
        "GitHub",
        dict(
            notification=dict(
                source="github",
                title="Build failed",
                body="Example repo · Tests",
                priority="important",
            )
        ),
    ),
    (
        "Calendar",
        dict(
            notification=dict(
                source="calendar",
                title="Team meeting",
                body="Starts in 10 minutes",
                priority="normal",
            )
        ),
    ),
    (
        "Home Assistant / Ring",
        dict(
            notification=dict(
                source="system",
                title="Front door activity (2)",
                body="Door opened · Someone is at the door",
                priority="normal",
            )
        ),
    ),
    ("Music", dict(music=dict(is_playing=True, title="Example song", artist="Example artist"))),
    (
        "TV / sports",
        dict(
            music=dict(
                video=dict(
                    app="YouTube",
                    title="Home vs Away · Highlights",
                    state="PLAYING",
                    reaction=dict(
                        reaction="excited",
                        sport="soccer",
                        prop="ball",
                        participants=[
                            dict(
                                name="Home",
                                short_name="HOM",
                                crest="",
                                colors=["#f0c040", "#ffffff"],
                            ),
                            dict(
                                name="Away",
                                short_name="AWY",
                                crest="",
                                colors=["#4080f0", "#ffffff"],
                            ),
                        ],
                    ),
                )
            )
        ),
    ),
    (
        "Codex completion",
        dict(
            notification=dict(
                source="system",
                title="Assistant setup",
                body="Codex finished. Ready to review.",
                priority="normal",
            )
        ),
    ),
    (
        "Focus timer",
        dict(
            notification=dict(
                source="system",
                title="Focus session finished",
                body="Time for a break.",
                priority="normal",
            )
        ),
    ),
    (
        "Alexa (planned)",
        dict(
            notification=dict(
                source="system",
                title="Alexa timer scheduled",
                body="Illustrative · awaiting account link",
                priority="normal",
            )
        ),
    ),
]
sheet = Image.new("RGB", (960, 4 * 350), "#101e25")
d = ImageDraw.Draw(sheet)
for i, (label, kwargs) in enumerate(cases):
    x, y = (i % 2) * 480, (i // 2) * 350
    sheet.paste(scene.render(style="okabe", phase=2, **kwargs), (x, y + 25))
    d.text((x + 12, y + 7), label, fill="white")
p = Path("docs/integration-gallery.png")
sheet.save(p)
print(p.resolve())

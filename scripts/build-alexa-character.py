#!/usr/bin/env python3
"""Generate non-private APL artwork using shared Pi sprites and the web room."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", choices=("okabe", "kurisu", "pip", "sonic"), default="okabe")
    parser.add_argument("--output", type=Path, default=Path(".local/alexa-skill/visuals"))
    parser.add_argument(
        "--set", dest="scene_set", help="One of the selected character's scene sets"
    )
    args = parser.parse_args()
    from pi import pip_face
    from okabebot.scene_sets import CATALOG, validate_selection

    selected = args.scene_set or CATALOG["characters"][args.character][0]
    validate_selection(args.character, selected)

    assets = {
        "frames": [
            pip_face.shapes(style=args.character, emotion="neutral", mouth=m, phase=p)
            for p in (1, 0)
            for m in (0, 0.5, 1)
        ]
    }
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "assets.json"
        source.write_text(json.dumps(assets))
        subprocess.run(
            [
                "node",
                str(Path(__file__).with_name("preview-alexa-character.cjs")),
                str(source),
                str(args.output),
                args.character,
                selected,
            ],
            check=True,
            timeout=30,
        )
    (args.output / "scene.json").write_text(
        json.dumps({"character": args.character, "set": selected, "presentation": "room"}) + "\n"
    )
    print("Generated generic scene frames for", args.character, "in", args.output)


if __name__ == "__main__":
    main()

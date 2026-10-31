#!/usr/bin/env python3
"""Build an offline satellite bundle, including the shared motion catalog."""

import argparse
from pathlib import Path
import shutil


def bundle(output):
    root = Path(__file__).resolve().parent.parent
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for path in (root / "pi").glob("*.py"):
        shutil.copy2(path, output / path.name)
    shutil.copytree(
        root / "okabebot/characters",
        output / "characters",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    old_catalog = output / "character-motion.json"
    if old_catalog.exists():
        old_catalog.unlink()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local/pi-bundle/pi"))
    print(bundle(parser.parse_args().output).resolve())

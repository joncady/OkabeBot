"""Shared declarative motion catalog; pixels remain in each surface adapter."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / "assets/character-motion.json").read_text())

"""Readable static instructions, compacted before inserting caller-owned data."""

from functools import lru_cache
from pathlib import Path
import re
from string import Template


@lru_cache(maxsize=64)
def source(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,70}", name):
        raise ValueError("Choose a bundled prompt")
    return (Path(__file__).parent / (name + ".md")).read_text().strip()


def prompt(name, **values):
    # Never minify dynamic user/source data or run provider text as a template.
    static = " ".join(source(name).split())
    return Template(static).substitute(values)

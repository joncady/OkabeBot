#!/usr/bin/env python3
"""Require a staged README update or an explicit review note per commit."""

import re
import subprocess
import sys
from pathlib import Path


def check(paths, message):
    if not paths or "README.md" in paths:
        return True
    return bool(re.search(r"^README-Reviewed: \S.{14,}$", message, re.MULTILINE))


def main():
    paths = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "-z"], text=True
    ).split("\0")
    paths = [p for p in paths if p]
    if check(paths, Path(sys.argv[1]).read_text()):
        return 0
    print(
        "README freshness check: stage the relevant README.md update, or add a commit trailer\n"
        "README-Reviewed: <why the current README still accurately describes this change>\n"
        "The hook checks review evidence; it cannot verify documentation semantics.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

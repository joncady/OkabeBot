#!/usr/bin/env python3
"""Reject known private trial artifact paths; not a personal-data content detector."""

import argparse
from pathlib import PurePosixPath
import subprocess
import sys


PRIVATE_PARTS = {".local", "amadeus-private", "amadeus-trials", "trial-results", "participant-data"}


def private_paths(paths):
    return [p for p in paths if set(PurePosixPath(p).parts) & PRIVATE_PARTS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracked", action="store_true", help="Audit tracked paths for CI")
    args = parser.parse_args()
    command = (
        ["git", "ls-files", "-z"]
        if args.tracked
        else ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    )
    paths = subprocess.check_output(command, text=True).split("\0")
    if private_paths(paths):
        # Avoid echoing paths that may themselves contain participant details.
        print(
            "Private trial artifact path rejected. Keep results in ignored local state. "
            "Commit core improvements, synthetic tests and declarative progress notes only.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

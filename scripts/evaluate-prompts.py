#!/usr/bin/env python3
"""Offline evaluator wrapper; run from the repository root."""

from pathlib import Path
import sys


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from okabebot.prompt_eval import cli

    cli()


if __name__ == "__main__":
    main()

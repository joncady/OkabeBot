#!/usr/bin/env python3
"""Audit built wheel/sdist contents without extracting them."""

import argparse
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile

PRIVATE_SUFFIXES = (
    ".local.json",
    ".pem",
    ".key",
    ".sqlite3",
    ".sqlite",
    ".log",
    ".wav",
    ".mp4",
    ".h264",
)
PRIVATE_PARTS = {".local", ".venv", "state", "__pycache__"}
KEY_BLOCK = re.compile(
    rb"(?m)^-----BEGIN [A-Z ]*PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{100,}-----END [A-Z ]*PRIVATE KEY-----"
)
TOKEN = re.compile(
    rb"\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{25,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"
)


def members(path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith("/"):
                    yield name, archive.read(name)
    else:
        with tarfile.open(path) as archive:
            for item in archive.getmembers():
                if item.isfile():
                    yield item.name, archive.extractfile(item).read()


def audit(path):
    errors = []
    names = []
    for name, raw in members(path):
        names.append(name)
        parts = PurePosixPath(name).parts
        if (
            any(p in PRIVATE_PARTS or p.startswith(".env") for p in parts)
            or name.endswith(PRIVATE_SUFFIXES)
            or ".." in parts
            or name.startswith("/")
        ):
            errors.append("Private/unsafe path: " + name)
        if KEY_BLOCK.search(raw) or TOKEN.search(raw):
            errors.append("Possible credential in: " + name)
    if path.suffix != ".whl":
        for required in (
            "scripts/start-linux.sh",
            ".agents/skills/okabebot-setup/SKILL.md",
            ".agents/skills/okabebot-setup/agents/openai.yaml",
            "pi/volume.py",
            "pi/assets/content-props.json",
            "docs/adapters.md",
        ):
            if not any(name.endswith("/" + required) for name in names):
                errors.append("Missing source resource: " + required)
    else:
        for required in (
            "okabebot/adapters/media.py",
            "okabebot/assets/leagues.json",
            "okabebot/web/app.js",
        ):
            if required not in names:
                errors.append("Missing package resource: " + required)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    paths = sorted(args.directory.glob("*.whl")) + sorted(args.directory.glob("*.tar.gz"))
    if not paths:
        parser.error("No built wheel/sdist found")
    failed = False
    for path in paths:
        errors = audit(path)
        failed |= bool(errors)
        print(path.name + (": FAIL" if errors else ": OK"))
        for error in errors:
            print("  " + error)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

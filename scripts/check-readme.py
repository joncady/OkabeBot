#!/usr/bin/env python3
"""Require README and deployment review evidence for relevant commits."""

import re
import subprocess
import sys
from pathlib import Path

TOPOLOGY_FILES = {
    "okabebot/config.py",
    "okabebot/runtime.py",
    "okabebot/bridge.py",
    "okabebot/local_conversation.py",
    "okabebot/local_worker.py",
    "okabebot/http_worker.py",
    "okabebot/speech.py",
    "okabebot/voice.py",
    "okabebot/server.py",
    "okabebot/controller_tools.py",
    "okabebot/arrival.py",
    "docs/devices.md",
    "docs/home-assistant.md",
    "docs/local-conversation.md",
    "docs/linux-controller.md",
    "docs/alexa.md",
    "docs/spotify.md",
    "docs/tv.md",
    "docs/ring.md",
    "docs/notifications.md",
}


def topology_check(paths, message):
    affected = any(
        p in TOPOLOGY_FILES
        or p.startswith(("pi/", "infra/", "examples/", "okabebot/adapters/"))
        or (p.startswith("scripts/") and Path(p).name.startswith(("start-", "install-", "qwen-")))
        for p in paths
    )
    if not affected or "docs/deployment.md" in paths:
        return True
    return bool(re.search(r"^Topology-Reviewed: \S.{14,}$", message, re.MULTILINE))


def check(paths, message):
    if not paths or "README.md" in paths:
        return True
    return bool(re.search(r"^README-Reviewed: \S.{14,}$", message, re.MULTILINE))


def main():
    paths = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "-z"], text=True
    ).split("\0")
    paths = [p for p in paths if p]
    message = Path(sys.argv[1]).read_text()
    if check(paths, message) and topology_check(paths, message):
        return 0
    print(
        "README freshness check: stage the relevant README.md update, or add a commit trailer\n"
        "README-Reviewed: <why the current README still accurately describes this change>\n"
        "Hosting/device/integration changes also require docs/deployment.md or\n"
        "Topology-Reviewed: <why the current inventory and diagram remain accurate>\n"
        "The hook checks review evidence; it cannot verify documentation semantics.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

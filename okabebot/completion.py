"""Codex notify adapter. Publishes names and IDs, never prompts or response text."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.request import Request, urlopen


def session_name(event, home):
    thread = event.get("thread-id", "")
    try:
        with sqlite3.connect(
            (home / "state_5.sqlite").as_uri() + "?mode=ro", uri=True, timeout=1
        ) as db:
            row = db.execute("SELECT title FROM threads WHERE id=?", (thread,)).fetchone()
            if row and row[0]:
                return " ".join(row[0].split())[:90]
    except (sqlite3.Error, OSError):
        pass
    return str(event.get("session-name") or Path(event.get("cwd") or "Codex").name or "Codex")[:90]


def payload(event, home):
    if event.get("type") != "agent-turn-complete":
        return None
    identifier = [event.get("thread-id"), event.get("turn-id")]
    if not identifier[1]:
        # Older clients omit turn-id; hash locally without publishing message text.
        identifier.append(event)
    key = hashlib.sha256(json.dumps(identifier, sort_keys=True).encode()).hexdigest()
    return dict(
        source="system",
        title=session_name(event, home),
        body="Codex finished. Ready to review on your laptop.",
        priority="normal",
        audio="chime",
        dedupe_key="codex:" + key,
        expires_at=time.time() + 300,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("event", help="JSON supplied by Codex notify")
    args = parser.parse_args(argv)
    settings = json.loads(args.settings.read_text())
    # Preserve the user's prior hook, independently of notification delivery.
    previous = settings.get("previous_notify", [])
    if previous:
        try:
            subprocess.run(
                previous + [args.event],
                timeout=15,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        event = json.loads(args.event)
        home = Path(
            settings.get("codex_home") or os.environ.get("CODEX_HOME") or Path.home() / ".codex"
        )
        data = payload(event, home)
        # Voice turns already have their own audiovisual response.
        if (
            not data
            or event.get("thread-id") in settings.get("exclude_threads", [])
            or event.get("client") in settings.get("exclude_clients", ["hardware_lab_ptt"])
        ):
            return 0
        token = Path(settings["token_file"]).read_text().strip()
        request = Request(
            settings["url"],
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json", "X-Notification-Token": token},
        )
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                raise OSError("Notification rejected")
    except (OSError, ValueError, KeyError, TypeError):
        print("OkabeBot completion notification unavailable.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run a command, then publish its outcome without sending output or arguments."""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="Task")
    parser.add_argument("--url", default="http://127.0.0.1:8768/notifications")
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply a command after --")
    start = time.monotonic()
    result = subprocess.run(command)
    elapsed = round(time.monotonic() - start)
    payload = dict(
        source="system",
        title=args.title[:80] + (" finished" if result.returncode == 0 else " failed"),
        body="Completed in %ss (exit %s)." % (elapsed, result.returncode),
        priority="normal" if result.returncode == 0 else "important",
        expires_at=time.time() + 300,
    )
    try:
        token = (Path(args.state_dir) / "notification-token").read_text().strip()
        request = urllib.request.Request(
            args.url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-Notification-Token": token},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise ValueError("Unexpected response")
    except Exception:
        print(
            "Command finished, but its notification could not be delivered. Check the controller URL and state directory.",
            file=sys.stderr,
        )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())

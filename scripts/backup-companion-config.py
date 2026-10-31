#!/usr/bin/env python3
"""Collect private read-only Pi diagnostics; optionally archive selected configuration.

Uses normal SSH host-key verification. Never flashes, reboots, upgrades or images
an active filesystem. Archives may contain secrets: keep the output private.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

COMMANDS = {
    "kernel": ["uname", "-a"],
    "memory": ["free", "-m"],
    "storage": ["df", "-h", "/", "/boot"],
    "power": ["vcgencmd", "get_throttled"],
    "temperature": ["vcgencmd", "measure_temp"],
    "failed_services": ["systemctl", "--failed", "--no-pager"],
}
# Only configuration. No raw recordings, reference audio, home directory or SSH keys.
ARCHIVE = ["boot/config.txt", "etc/fstab", "etc/ssh/sshd_config", "etc/systemd/system"]


def connection(target, identity):
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+", target) or target.startswith("-"):
        raise ValueError("Use an explicit user@hostname SSH target")
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-i",
        str(identity),
        target,
    ]


def collect(target, identity, output, archive=False):
    ssh = connection(target, identity)
    output = Path(output)
    if output.exists():
        raise ValueError("Choose a new output directory; existing backups are never replaced")
    output.mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    report = {}
    for name, command in COMMANDS.items():
        try:
            result = subprocess.run(ssh + command, capture_output=True, timeout=25)
            report[name] = {
                "exit_code": result.returncode,
                "output": result.stdout.decode(errors="replace")[:16000],
                "error": result.stderr.decode(errors="replace")[:2000],
            }
        except subprocess.TimeoutExpired:
            report[name] = {"error": "Timed out; no automatic retry"}
    path = output / "diagnostics.json"
    with path.open("x") as stream:
        os.chmod(path, 0o600)
        json.dump(report, stream, indent=2)
    if archive:
        path = output / "configuration.tar.gz"
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            result = subprocess.run(
                ssh + ["tar", "-C", "/", "-czf", "-", *ARCHIVE],
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=90,
            )
        if result.returncode:
            path.rename(output / "configuration.partial.tar.gz")
            raise RuntimeError(
                "Configuration archive is incomplete; inspect the private partial archive"
            )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="user@hostname with an already verified SSH host key")
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New private, ignored directory")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Also save selected configuration, possibly containing secrets",
    )
    args = parser.parse_args()
    collect(args.target, args.identity, args.output, args.archive)
    print("Private collection saved. This is not a full card backup; no device state was changed.")


if __name__ == "__main__":
    main()

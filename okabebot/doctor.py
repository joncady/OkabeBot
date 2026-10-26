"""Read-only prerequisite checks for a controller, with optional device probes."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import sys

from .config import get_config


def check(config, devices=False):
    results = []

    def add(name, ok, detail):
        results.append(dict(name=name, ok=bool(ok), detail=detail))

    add(
        "python",
        sys.version_info >= (3, 10) and struct.calcsize("P") == 8,
        "64-bit Python 3.10+ required",
    )
    modules = ["mcp", "PIL", "faster_whisper"]
    if config["spotify"]["source"] == "cast":
        modules.append("pychromecast")
    if config["notifications"]["calendar"]:
        modules.extend(["icalendar", "recurring_ical_events"])
    for module in modules:
        add(module, importlib.util.find_spec(module) is not None, "Python dependency")
    binary = config["codex"]["binary"]
    add("codex", bool(shutil.which(binary)), "Install Codex for this OS and complete codex login")
    commands = ["say", "afconvert"] if sys.platform == "darwin" else ["espeak-ng", "ffmpeg"]
    if any(d["transport"] == "ssh" for d in config["devices"].values()):
        commands.append("ssh")
    if config["notifications"]["github"]:
        commands.append("gh")
    for command in commands:
        add(command, bool(shutil.which(command)), "System dependency")
    folder = Path(config["state_dir"])
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    add(
        "state-directory",
        folder.is_dir() and os.access(folder, os.W_OK),
        "Writable persistent state location",
    )
    if devices:
        from .transport import device

        for name in config["devices"]:
            try:
                response = device(name).rpc({"op": "status"})
                add(name, not response.get("error"), "Read-only device health")
            except Exception:
                add(
                    name,
                    False,
                    "Device unavailable; verify service, SSH authorization and host key locally",
                )
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument(
        "--devices", action="store_true", help="Probe device status without operating hardware"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.config:
        os.environ["OKABEBOT_CONFIG"] = str(Path(args.config).expanduser().resolve())
        get_config.cache_clear()
    try:
        results = check(get_config(), args.devices)
    except (OSError, ValueError):
        results = [
            dict(
                name="configuration",
                ok=False,
                detail="Configuration missing or invalid; check it locally",
            )
        ]
    if args.json:
        print(json.dumps(results))
    else:
        for result in results:
            print(
                ("OK " if result["ok"] else "MISSING ") + result["name"] + ": " + result["detail"]
            )
        print("These checks do not verify account sign-in, model availability or live interaction.")
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

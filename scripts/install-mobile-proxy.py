#!/usr/bin/env python3
"""Install the route-limited mobile proxy as a macOS login service.

Install the controller package first; this does not deploy source, sign in,
enable HTTPS, overwrite existing Serve routes or expose public Funnel.
"""

import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path.home() / "Library/Application Support/OkabeBot"
    )
    parser.add_argument(
        "--tailscale", default="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Use your platform's service manager outside macOS")
    status = json.loads(subprocess.check_output([args.tailscale, "status", "--json"]))
    if status.get("BackendState") != "Running":
        parser.error("Sign in to Tailscale first")
    hostname = status["Self"]["DNSName"].rstrip(".")
    root = args.root.resolve()
    python = root / ".venv/bin/python"
    module = root / "okabebot/mobile_proxy.py"
    if not python.is_file() or not module.is_file():
        parser.error("Install this controller version before creating its proxy service")
    label = "dev.okabebot.mobile-proxy"
    path = Path.home() / "Library/LaunchAgents" / (label + ".plist")
    if args.check:
        print("Tailscale connected; proxy module installed; login service present:", path.is_file())
        return
    if path.exists():
        parser.error("Proxy login service already exists; inspect it before replacing")
    logs = root / ".local/mobile"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        plistlib.dumps(
            {
                "Label": label,
                "ProgramArguments": [
                    str(python),
                    "-m",
                    "okabebot.mobile_proxy",
                    "--hostname",
                    hostname,
                ],
                "WorkingDirectory": str(root),
                "RunAtLoad": True,
                "KeepAlive": True,
                "StandardOutPath": str(logs / "proxy-out.log"),
                "StandardErrorPath": str(logs / "proxy-error.log"),
            }
        )
    )
    path.chmod(0o600)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True)
    print(
        "Installed loopback proxy on 8772. Inspect tailscale serve status, then enable private HTTPS Serve if unused."
    )


if __name__ == "__main__":
    main()

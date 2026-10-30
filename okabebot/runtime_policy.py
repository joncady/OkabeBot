"""Persistent user-session startup policy; no pre-login or lid-closed guarantee."""

import os
import plistlib
from pathlib import Path
import subprocess
import sys
from .presence_control import read, write

DEFAULTS = {"prevent_sleep_on_ac": False, "docker_at_login": False}
DOCKER_LABEL = "com.okabebot.docker-login"


def settings(folder):
    return {**DEFAULTS, **read(Path(folder) / "runtime/policy.json", {})}


def docker_login(enabled):
    if sys.platform != "darwin":
        raise ValueError("Docker login startup is macOS-only")
    path = Path.home() / "Library/LaunchAgents" / (DOCKER_LABEL + ".plist")
    domain = "gui/" + str(os.getuid())
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            plistlib.dumps(
                {
                    "Label": DOCKER_LABEL,
                    "ProgramArguments": ["/usr/bin/open", "-g", "-j", "-a", "Docker"],
                    "RunAtLoad": True,
                }
            )
        )
        path.chmod(0o600)
        loaded = subprocess.run(
            ["launchctl", "print", domain + "/" + DOCKER_LABEL], capture_output=True
        )
        if loaded.returncode:
            subprocess.run(
                ["launchctl", "bootstrap", domain, str(path)], check=True, capture_output=True
            )
    else:
        subprocess.run(["launchctl", "bootout", domain + "/" + DOCKER_LABEL], capture_output=True)
        path.unlink(missing_ok=True)


def configure(folder, data):
    if (
        not isinstance(data, dict)
        or not data
        or set(data) - set(DEFAULTS)
        or any(type(v) is not bool for v in data.values())
    ):
        raise ValueError("Use boolean startup settings")
    cfg = {**settings(folder), **data}
    if "docker_at_login" in data:
        docker_login(cfg["docker_at_login"])
    write(Path(folder) / "runtime/policy.json", cfg)
    return cfg

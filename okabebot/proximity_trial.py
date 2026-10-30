"""Opt-in bounded Pi proximity trial. No persistent scanner or location history."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess

from .config import get_config
from .controller_tools import request
from .transport import Device


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--follow", action="store_true", help="Allow one proximity-triggered move")
    args = parser.parse_args()
    if not 5 <= args.seconds <= 900:
        parser.error("Use a bounded 5–900 second trial")
    settings = json.loads(args.settings.read_text())
    state = request()
    if state["surfaces"]["phase"] not in ("pi", "tv") or not state["surfaces"]["current_location"]:
        raise ValueError("Wait for the current character handoff to finish")
    destination = settings["destination"]
    if not any(
        p["id"] == destination and p["adapter"] == "pi" for p in state["surfaces"]["locations"]
    ):
        raise ValueError("Choose a configured Pi companion destination")
    endpoint = get_config()["devices"]["display"]
    if endpoint["transport"] != "ssh":
        raise ValueError("This initial trial uses an SSH-connected Pi scanner")
    remote = endpoint["remote_dir"] + "/ble_proximity.py"
    command = "python3 " + shlex.quote(remote) + " --seconds " + str(args.seconds)
    moved = False
    initial = state["surfaces"]["current_location"]
    manual_override = False
    process = subprocess.Popen(
        Device(endpoint).ssh_args() + [endpoint["ssh_target"], command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        # Destination and authority stay on the controller; the Pi sees beacon settings only.
        process.stdin.write(
            json.dumps({k: v for k, v in settings.items() if k != "destination"}) + "\n"
        )
        process.stdin.close()
        for line in process.stdout:
            event = json.loads(line)
            if event.get("state") == "near" and args.follow and not moved and not manual_override:
                state = request()
                current = state["surfaces"]["current_location"]
                if current not in (initial, destination):
                    manual_override = True
                    print(json.dumps({"state": "manual_override"}), flush=True)
                elif (
                    current != destination
                    and not state["busy"]
                    and state["surfaces"]["phase"] in ("pi", "tv")
                ):
                    moved = True  # No blind retries of an ambiguous handoff.
                    request("/surfaces/move", {"location_id": destination})
                    print(json.dumps({"state": "move_requested"}), flush=True)
            print(json.dumps(event), flush=True)
        if process.wait(timeout=10):
            raise RuntimeError("Pi BLE trial ended unsuccessfully")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()

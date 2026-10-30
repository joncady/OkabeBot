"""Bounded two-screen presence proof; explicit config, no location history."""

import json
import time


class FollowGate:
    def __init__(self, locations, cooldown=120):
        self.locations = set(locations)
        self.cooldown = cooldown
        self.last_move = None
        self.near_until = 0
        self.worn_until = 0

    def worn(self, value, now):
        self.worn_until = now + 120 if value is True else 0

    def choose(self, target, state, now, near=False):
        if near:
            self.near_until = now + 30
        if now >= self.worn_until or target not in self.locations:
            return False
        surfaces = state.get("surfaces", {})
        if (
            state.get("busy")
            or state.get("recording")
            or surfaces.get("phase") not in ("pi", "tv")
            or surfaces.get("current_location") not in self.locations
            or surfaces.get("current_location") == target
        ):
            return False
        if not near and now < self.near_until:
            return False
        # Explicit playback only; do not wake/interrupt a known playing TV.
        media = state.get("media", {})
        if (
            state.get("focus", {}).get("active")
            or state.get("music", {}).get("is_playing")
            or state.get("tv", {}).get("is_playing")
            or state.get("tv", {}).get("player_state") in ("PLAYING", "BUFFERING")
            or media.get("is_playing")
            or media.get("state") in ("playing", "buffering")
        ):
            return False
        if self.last_move is not None and now - self.last_move < self.cooldown:
            return False
        self.last_move = now  # Consume before request: never blindly retry a handoff.
        return True


def main():
    import argparse
    import queue
    import subprocess
    import threading
    import urllib.request
    from pathlib import Path
    import paho.mqtt.client as mqtt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    events = queue.Queue(maxsize=100)
    gate = FollowGate([cfg["pi_location"], cfg["tv_location"]])

    def request(path="/state", data=None):
        control = json.loads(Path(cfg["control_file"]).read_text())
        base, token = control["url"].split("#", 1)
        req = urllib.request.Request(
            base.rstrip("/") + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"X-Hardware-Token": token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)

    def enqueue(value):
        try:
            events.put_nowait(value)
        except queue.Full:
            pass

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(cfg["username"], cfg["password"])
    client.on_connect = lambda client, *a: client.subscribe(
        [(cfg["motion_topic"], 0), (cfg["body_topic"], 0)]
    )

    def message(client, userdata, msg):
        if msg.retain:
            return
        try:
            value = json.loads(msg.payload)
            # Event timestamp is produced by HA; stale or queued events never move.
            if msg.topic == cfg["body_topic"]:
                if 0 <= time.time() - value["at"] < 20:
                    gate.worn(value.get("worn"), time.monotonic())
                return
            if value.get("occupied") is True and 0 <= time.time() - value["at"] < 20:
                enqueue((cfg["tv_location"], False, time.monotonic()))
        except (ValueError, TypeError, KeyError):
            pass

    client.on_message = message
    client.connect(cfg["host"], cfg.get("port", 1883), 30)
    client.loop_start()
    process = subprocess.Popen(
        cfg["scanner_argv"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    process.stdin.write(json.dumps(cfg["beacon"]) + "\n")
    process.stdin.close()

    def samples():
        for line in process.stdout:
            try:
                value = json.loads(line)
                if "rssi" in value:
                    print("Watch RSSI: " + str(value["rssi"]), flush=True)
                if value.get("state") in ("target_seen", "near"):
                    print("Watch beacon: " + value["state"], flush=True)
                if value.get("state") == "near":
                    enqueue((cfg["pi_location"], True, time.monotonic()))
                elif (
                    value.get("state") == "sample"
                    and value.get("rssi", -127) >= cfg["beacon"]["enter"]
                ):
                    enqueue((None, True, time.monotonic()))
            except (ValueError, TypeError):
                pass

    threading.Thread(target=samples, daemon=True).start()
    try:
        while process.poll() is None:
            try:
                target, near, observed = events.get(timeout=1)
            except queue.Empty:
                continue
            if time.monotonic() - observed > 5:
                continue
            if near:
                gate.near_until = time.monotonic() + 30
            if target is None:
                continue
            try:
                state = request()
                if gate.choose(target, state, time.monotonic(), near):
                    request("/surfaces/move", {"location_id": target})
                    print("Presence handoff requested", flush=True)
            except Exception:
                print("Presence handoff unavailable; no retry", flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()

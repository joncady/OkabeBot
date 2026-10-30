"""Bounded two-anchor BLE follow proof; no persistent location history."""

import statistics
from collections import deque
import math

from .service_runtime import stopping, stop_process


class AnchorGate:
    def __init__(self, locations, threshold=-85, margin=8, window=30, dwell=6, cooldown=120):
        locations = tuple(locations)
        if (
            len(locations) != 2
            or len(set(locations)) != 2
            or not all(isinstance(v, str) and v for v in locations)
            or not all(
                type(v) in (int, float) and math.isfinite(v)
                for v in (threshold, margin, window, dwell, cooldown)
            )
            or not -100 <= threshold <= -20
            or not 1 <= margin <= 30
            or not 10 <= window <= 60
            or not 1 <= dwell <= 30
            or not 30 <= cooldown <= 3600
        ):
            raise ValueError("Invalid anchor configuration")
        self.locations = locations
        self.threshold, self.margin, self.window = threshold, margin, window
        self.dwell, self.cooldown = dwell, cooldown
        self.samples = {location: deque(maxlen=256) for location in locations}
        self.candidate = None
        self.since = 0
        self.last_move = None
        self.last_check = None

    def update(self, location, rssi, now):
        if location not in self.samples or type(rssi) not in (int, float) or not -127 <= rssi <= 0:
            return
        self.samples[location].append((now, rssi))

    def evidence(self, now):
        """Current bounded radio diagnostics, without beacon identity or history."""
        result = {}
        for place, samples in self.samples.items():
            recent = [(stamp, rssi) for stamp, rssi in samples if 0 <= now - stamp <= self.window]
            result[place] = {
                "samples": len(recent),
                "age_seconds": round(now - recent[-1][0], 1) if recent else None,
                "median_rssi": statistics.median(rssi for _, rssi in recent) if recent else None,
            }
        return result

    def nearby(self, now, threshold=-75):
        """Fresh, strong, unambiguous anchor evidence, independent of movement cooldown."""
        levels = {}
        for place, samples in self.samples.items():
            recent = [(stamp, rssi) for stamp, rssi in samples if 0 <= now - stamp <= self.window]
            if len(recent) >= 3 and 0 <= now - recent[-1][0] <= 10:
                levels[place] = statistics.median(rssi for _, rssi in recent)
        if not levels:
            return None
        winner = max(levels, key=levels.get)
        if levels[winner] < threshold:
            return None
        for other, samples in self.samples.items():
            recent = [rssi for stamp, rssi in samples if 0 <= now - stamp <= self.window]
            if (
                other != winner
                and recent
                and levels[winner] - statistics.median(recent) < self.margin
            ):
                return None
        return winner

    def choose(self, now, current, blocked=False):
        if self.last_check is not None and now - self.last_check > self.window:
            self.candidate = None
        self.last_check = now
        levels = {}
        for place, samples in self.samples.items():
            while samples and now - samples[0][0] > self.window:
                samples.popleft()
            if len(samples) >= 3 and now - samples[-1][0] <= 10:
                levels[place] = statistics.median(value for _, value in samples)
        ranked = sorted(levels, key=levels.get, reverse=True)
        winner = ranked[0] if ranked and levels[ranked[0]] >= self.threshold else None
        # Even a small number of recent competing samples must count as evidence.
        if winner:
            for other, samples in self.samples.items():
                if (
                    other != winner
                    and samples
                    and levels[winner] - statistics.median(value for _, value in samples)
                    < self.margin
                ):
                    winner = None
                    break
        if blocked or current not in self.locations or winner is None:
            self.candidate = None
            return None
        if winner != self.candidate:
            self.candidate, self.since = winner, now
            return None
        if (
            winner == current
            or now - self.since < self.dwell
            or self.last_move is not None
            and now - self.last_move < self.cooldown
        ):
            return None
        self.last_move = now  # Consume before physical request; uncertain moves are not retried.
        return winner


def run(stop):
    import argparse
    import json
    import queue
    import subprocess
    import threading
    import time
    import urllib.request
    from pathlib import Path
    import paho.mqtt.client as mqtt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=900)
    args = parser.parse_args()
    if not 60 <= args.seconds <= 1800:
        parser.error("Use a 60–1800 second bounded trial")
    cfg = json.loads(args.config.read_text())
    locations = [a["location_id"] for a in cfg["anchors"]]
    if len(locations) != 2 or len(set(locations)) != 2:
        raise ValueError("Choose exactly two distinct approved destinations")
    gate = AnchorGate(locations, **cfg.get("gate", {}))
    samples = queue.Queue(maxsize=200)
    worn = [0.0]
    processes = []

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

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(cfg["username"], cfg["password"])
    client.on_connect = lambda client, *a: client.subscribe(cfg["body_topic"])

    def message(client, userdata, msg):
        if msg.retain:
            return
        try:
            value = json.loads(msg.payload)
            if 0 <= time.time() - value["at"] < 20:
                worn[0] = time.monotonic() + 90 if value.get("worn") is True else 0
        except (ValueError, TypeError, KeyError):
            pass

    def reader(process, location):
        for line in process.stdout:
            try:
                value = json.loads(line)
                if "rssi" in value:
                    samples.put_nowait((location, value["rssi"], time.monotonic()))
            except (ValueError, TypeError, queue.Full):
                pass

    client.on_message = message
    client.max_queued_messages_set(16)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.connect_async(cfg["host"], cfg.get("port", 1883), 30)
    client.loop_start()
    deadline = time.monotonic() + args.seconds
    try:
        initial = request()
        registered = {p["id"] for p in initial["surfaces"]["locations"]}
        if not set(locations) <= registered:
            raise ValueError("Unknown configured destination")
        for anchor in cfg["anchors"]:
            process = subprocess.Popen(
                anchor["scanner_argv"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            processes.append(process)
            process.stdin.write(json.dumps(cfg["beacon"]) + "\n")
            process.stdin.close()
            threading.Thread(
                target=reader, args=(process, anchor["location_id"]), daemon=True
            ).start()
        had_controller_error = False
        while not stop.is_set() and time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                print("Scanner stopped; following disabled", flush=True)
                break
            try:
                place, rssi, observed = samples.get(timeout=1)
                gate.update(place, rssi, observed)
                while not samples.empty():
                    place, rssi, observed = samples.get_nowait()
                    gate.update(place, rssi, observed)
            except queue.Empty:
                pass
            now = time.monotonic()
            try:
                state = request()
            except Exception:
                gate.candidate = None
                if not had_controller_error:
                    print("Controller unavailable; following paused", flush=True)
                had_controller_error = True
                stop.wait(2)
                continue
            if had_controller_error:
                print("Controller recovered; requiring new dwell", flush=True)
                gate.candidate = None
                had_controller_error = False
            surfaces = state["surfaces"]
            blocked = (
                stop.is_set()
                or (cfg.get("require_worn", True) and now >= worn[0])
                or state.get("busy")
                or state.get("recording")
                or state.get("focus", {}).get("active")
                or surfaces.get("phase") not in ("pi", "tv")
                or state.get("music", {}).get("is_playing")
                or state.get("tv", {}).get("is_playing")
                or state.get("tv", {}).get("player_state") in ("PLAYING", "BUFFERING")
            )
            target = gate.choose(now, surfaces.get("current_location"), blocked)
            if target:
                print("Requesting presence handoff to " + target, flush=True)
                try:
                    request("/surfaces/move", {"location_id": target})
                except Exception:
                    print("Handoff uncertain; no immediate retry", flush=True)
    finally:
        for process in processes:
            stop_process(process)
        client.disconnect()
        client.loop_stop()


def main():
    with stopping() as stop:
        run(stop)


if __name__ == "__main__":
    main()

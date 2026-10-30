"""Read-only two-anchor home estimate and explicitly armed return greeting."""

import json
import statistics
import time
from collections import deque
from pathlib import Path

from .service_runtime import stopping, stop_process
from .presence_follow_service import Following
from . import presence_control


class HomeGate:
    def __init__(self, anchors, absence=300):
        self.anchors = tuple(anchors)
        self.absence = absence
        self.beats = {}
        self.samples = deque(maxlen=256)
        self.last_seen = None
        self.door = None
        self.intent = None
        self.healthy_since = None

    def observe(self, anchor, event, now):
        if anchor not in self.anchors:
            return
        if event.get("state") in ("unavailable", "stopped"):
            self.beats.pop(anchor, None)
            return
        if event.get("state") in ("scanning", "heartbeat", "sample", "near", "target_seen"):
            self.beats[anchor] = now
        rssi = event.get("rssi")
        if type(rssi) in (int, float) and -127 <= rssi <= 0:
            self.samples.append((now, rssi))
            self.last_seen = now

    def estimate(self, now):
        healthy = all(0 <= now - self.beats.get(a, -1e9) <= 15 for a in self.anchors)
        if not healthy:
            self.healthy_since = None
            return "unknown"
        if self.healthy_since is None:
            self.healthy_since = now
        while self.samples and now - self.samples[0][0] > 30:
            self.samples.popleft()
        if (
            len(self.samples) >= 3
            and now - self.samples[-1][0] <= 15
            and statistics.median(v for _, v in self.samples) >= -95
        ):
            return "home"
        if self.last_seen is not None and now - self.last_seen < 90:
            return "home"
        departure = max(
            v for v in (self.intent, self.door, self.last_seen, self.healthy_since) if v is not None
        )
        departure_evidence = self.intent is not None or (
            self.door is not None
            and self.last_seen is not None
            and self.door >= self.last_seen - 120
        )
        if departure_evidence and now - departure >= self.absence:
            return "probably_away"
        return "unknown"


def return_ready(state, saved, door, now, wall):
    return bool(
        state == "home"
        and saved.get("away_since")
        and not saved.get("welcomed")
        and door is not None
        and 0 <= now - door <= 180
        and 120 <= wall - saved["away_since"] <= 90 * 86400
    )


def main():
    import argparse
    import queue
    import subprocess
    import threading
    import urllib.request
    from paho.mqtt import client as mqtt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    cfg = json.loads(parser.parse_args().config.read_text())
    nearby_threshold = cfg.get("nearby_threshold", -75)
    if type(nearby_threshold) not in (int, float) or not -95 <= nearby_threshold <= -40:
        raise ValueError("nearby_threshold must be -95 to -40 dBm")
    folder = Path(cfg["state_file"])
    saved = json.loads(folder.read_text()) if folder.exists() else {}
    following = Following(folder.parent.parent, cfg)
    gate = HomeGate([a["id"] for a in cfg["anchors"]])
    # Explicit one-trip departure intent comes from owner configuration, not missing packets.
    if cfg.get("departure_intent") and not saved.get("welcomed"):
        gate.intent = time.monotonic()
    events = queue.Queue(maxsize=500)
    processes = []
    prefix = cfg["prefix"]

    def save():
        temp = folder.with_suffix(".tmp")
        temp.write_text(json.dumps(saved))
        temp.chmod(0o600)
        temp.replace(folder)

    def enqueue(event):
        try:
            events.put_nowait(event)
        except queue.Full:
            pass

    with stopping() as stop:

        def scanner(anchor):
            while not stop.is_set():
                process = subprocess.Popen(
                    anchor["argv"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                processes.append(process)
                try:
                    process.stdin.write(json.dumps(cfg["beacon"]) + "\n")
                    process.stdin.close()
                    for line in process.stdout:
                        try:
                            enqueue((anchor["id"], json.loads(line), time.monotonic()))
                        except ValueError:
                            pass
                        if stop.is_set():
                            break
                except (OSError, ValueError):
                    pass
                finally:
                    stop_process(process)
                    processes.remove(process)
                stop.wait(5)

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg["id"])
        client.username_pw_set(cfg["username"], cfg["password"])
        client.will_set(prefix + "/availability", "offline", qos=1, retain=True)
        client.max_queued_messages_set(16)
        client.reconnect_delay_set(1, 60)

        def connected(client, userdata, flags, reason, props):
            if reason.is_failure:
                return
            client.publish(prefix + "/availability", "offline", qos=1, retain=True)
            client.publish(
                "homeassistant/sensor/" + cfg["id"] + "/presence/config",
                json.dumps(
                    {
                        "name": "Watch home estimate",
                        "unique_id": cfg["id"] + "_presence",
                        "state_topic": prefix + "/state",
                        "value_template": "{{ value_json.presence }}",
                        "availability_topic": prefix + "/availability",
                        "expire_after": 45,
                        "json_attributes_topic": prefix + "/state",
                        "device": {
                            "identifiers": [cfg["id"]],
                            "name": "Watch BLE presence",
                            "manufacturer": "OkabeBot",
                            "model": "Two-anchor device presence",
                        },
                    }
                ),
                qos=1,
                retain=True,
            )
            client.subscribe(cfg["door_topic"])

        def message(client, userdata, msg):
            if msg.retain:
                return
            try:
                value = json.loads(msg.payload)
                if value.get("open") is True and 0 <= time.time() - value["at"] < 20:
                    enqueue(("door", {}, time.monotonic()))
            except (ValueError, TypeError, KeyError):
                pass

        client.on_connect = connected
        client.on_message = message
        client.connect_async(cfg["host"], cfg.get("port", 1883), 30)
        client.loop_start()
        threads = []
        for anchor in cfg["anchors"]:
            thread = threading.Thread(target=scanner, args=(anchor,), daemon=True)
            threads.append(thread)
            thread.start()
        last_publish = 0
        try:
            while not stop.is_set():
                try:
                    anchor, event, observed = events.get(timeout=1)
                    if time.monotonic() - observed <= 10:
                        if anchor == "door":
                            gate.door = observed
                        else:
                            gate.observe(anchor, event, observed)
                            if "rssi" in event:
                                following.gate.update(anchor, event["rssi"], observed)
                except queue.Empty:
                    pass
                now = time.monotonic()
                state = gate.estimate(now)
                if state == "probably_away" and (
                    not saved.get("away_since") or saved.get("welcomed")
                ):
                    departure = gate.last_seen if gate.last_seen is not None else gate.intent
                    saved["away_since"] = time.time() - max(0, now - (departure or now))
                    saved["welcomed"] = False
                    save()
                if return_ready(state, saved, gate.door, now, time.time()):
                    # Persist consumption before POST. Never retry uncertain speech.
                    saved["welcomed"] = True
                    gate.intent = None
                    save()
                    try:
                        control = json.loads(Path(cfg["control_file"]).read_text())
                        base = control["url"].split("#", 1)[0].rstrip("/")
                        token = Path(cfg["arrival_token_file"]).read_text().strip()
                        req = urllib.request.Request(
                            base + "/arrivals",
                            data=json.dumps(
                                {
                                    "trigger": "ble_presence",
                                    "away_since": saved["away_since"],
                                    "arrived_at": time.time(),
                                }
                            ).encode(),
                            headers={"X-Arrival-Token": token, "Content-Type": "application/json"},
                        )
                        with urllib.request.urlopen(req, timeout=10) as response:
                            result = json.load(response)
                        print(
                            "Return greeting queued: " + str(bool(result.get("queued"))), flush=True
                        )
                    except Exception:
                        print("Return greeting unavailable; not replayed", flush=True)
                healthy = sum(0 <= now - gate.beats.get(a, -1e9) <= 15 for a in gate.anchors)
                runtime = {
                    "updated_at": time.time(),
                    "presence": state,
                    "healthy_scanners": healthy,
                    "nearby_location": following.gate.nearby(now, cfg.get("nearby_threshold", -75)),
                    "nearby_evidence": following.gate.evidence(now),
                    "follow_reason": following.reason,
                }
                presence_control.write(folder.parent / "runtime.json", runtime)
                runtime["follow_reason"] = following.step(now, healthy)
                presence_control.write(folder.parent / "runtime.json", runtime)
                if time.monotonic() - last_publish >= 15 and client.is_connected():
                    client.publish(
                        prefix + "/state",
                        json.dumps(
                            {
                                "presence": state,
                                "healthy_scanners": sum(
                                    0 <= time.monotonic() - gate.beats.get(a, -1e9) <= 15
                                    for a in gate.anchors
                                ),
                            }
                        ),
                        qos=1,
                        retain=False,
                    )
                    client.publish(prefix + "/availability", "online", qos=1, retain=True)
                    last_publish = time.monotonic()
                stop.wait(0.1)
        finally:
            stop.set()
            for process in list(processes):
                stop_process(process)
            for thread in threads:
                thread.join(timeout=6)
            client.disconnect()
            client.loop_stop()


if __name__ == "__main__":
    main()

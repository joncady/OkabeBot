"""Opt-in MQTT facade for an existing controller; never publishes conversation content."""

import argparse
import json
import math
import urllib.request
from pathlib import Path

from .service_runtime import stopping


def command(name, payload, location):
    """A deliberately small command allowlist; retained commands are rejected by caller."""
    if name == "call" and payload == "PRESS":
        return "/surfaces/move", {"location_id": location}
    if name == "volume":
        value = float(payload)
        if math.isfinite(value) and 0 <= value <= 100 and value.is_integer():
            return "/speaker/volume", {"percent": int(value)}
    raise ValueError("Unsupported companion command")


def discovery(prefix, identity, name, area):
    device = {
        "identifiers": [identity],
        "name": name,
        "manufacturer": "OkabeBot",
        "model": "Companion satellite",
        "suggested_area": area,
    }
    for kind, key, label, template in [
        ("sensor", "character", "Character", "{{ value_json.character }}"),
        ("sensor", "status", "Status", "{{ value_json.status }}"),
        ("binary_sensor", "busy", "Busy", "{{ value_json.busy }}"),
        ("binary_sensor", "recording", "Recording", "{{ value_json.recording }}"),
        (
            "binary_sensor",
            "voice_connected",
            "Voice service connected",
            "{{ value_json.voice_connected }}",
        ),
        (
            "binary_sensor",
            "display_connected",
            "Display service connected",
            "{{ value_json.display_connected }}",
        ),
        ("binary_sensor", "mac_screen", "Mac display awake", "{{ value_json.mac_screen }}"),
        ("number", "volume", "Speaker volume", "{{ value_json.volume }}"),
        ("button", "call", "Call companion", None),
    ]:
        config = {
            "name": label,
            "unique_id": identity + "_" + key,
            "device": device,
            "availability_topic": prefix + "/availability",
        }
        if template:
            config.update(state_topic=prefix + "/state", value_template=template)
        if kind == "binary_sensor":
            config.update(payload_on=True, payload_off=False)
        if kind in ("button", "number"):
            config["command_topic"] = prefix + "/command/" + key
        if kind == "number":
            config.update(min=0, max=100, step=1, mode="slider")
        if key == "mac_screen":
            config["device"] = {
                "identifiers": [identity + "_mac"],
                "name": "Little Lab Mac",
                "manufacturer": "OkabeBot",
                "model": "Native Mac companion",
            }
            config["value_template"] = (
                "{{ value_json.mac_screen if value_json.mac_screen in ['on','off'] else 'unknown' }}"
            )
            config.pop("availability_topic")
            config["availability"] = [
                {"topic": prefix + "/availability"},
                {
                    "topic": prefix + "/state",
                    "value_template": "{{ 'online' if value_json.mac_screen in ['on','off'] else 'offline' }}",
                },
            ]
            config["availability_mode"] = "all"
            config.update(payload_on="on", payload_off="off", expire_after=75)
        yield "homeassistant/" + kind + "/" + identity + "/" + key + "/config", config


def room_discovery(prefix, identity, name, area):
    device = {
        "identifiers": [identity],
        "name": name,
        "manufacturer": "OkabeBot",
        "model": "Companion satellite",
        "suggested_area": area,
    }
    for kind, key, label, extra in [
        (
            "sensor",
            "distance_mm",
            "Ultrasonic distance",
            {"device_class": "distance", "unit_of_measurement": "mm", "state_class": "measurement"},
        ),
        (
            "sensor",
            "temperature_c",
            "Room temperature",
            {
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "state_class": "measurement",
            },
        ),
        (
            "sensor",
            "humidity_percent",
            "Room humidity",
            {"device_class": "humidity", "unit_of_measurement": "%", "state_class": "measurement"},
        ),
        (
            "binary_sensor",
            "tilt_closed",
            "Tilt contact",
            {"payload_on": True, "payload_off": False},
        ),
        (
            "binary_sensor",
            "nearby",
            "Ultrasonic proximity",
            {"device_class": "occupancy", "payload_on": True, "payload_off": False},
        ),
    ]:
        yield (
            "homeassistant/" + kind + "/" + identity + "/" + key + "/config",
            {
                "name": label,
                "unique_id": identity + "_" + key,
                "device": device,
                "state_topic": prefix + "/state",
                "value_template": "{{ value_json." + key + " }}",
                "availability": [
                    {"topic": prefix + "/availability"},
                    {
                        "topic": prefix + "/state",
                        "value_template": "{{ 'online' if value_json."
                        + key
                        + " is not none else 'offline' }}",
                    },
                ],
                "availability_mode": "all",
                "expire_after": 45,
                **extra,
            },
        )


def run(stop):
    from paho.mqtt import client as mqtt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    prefix = "okabebot/" + cfg["id"]

    def request(path, data=None):
        control = json.loads(Path(cfg["control_file"]).read_text())
        base, token = control["url"].split("#", 1)
        req = urllib.request.Request(
            base.rstrip("/") + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"X-Hardware-Token": token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg["id"])
    client.username_pw_set(cfg["username"], cfg["password"])
    client.will_set(prefix + "/availability", "offline", qos=1, retain=True)

    def connected(client, userdata, flags, reason, properties):
        if reason.is_failure:
            return
        client.publish(prefix + "/availability", "offline", qos=1, retain=True)
        for topic, value in [
            *discovery(prefix, cfg["id"], cfg["name"], cfg["area"]),
            *room_discovery(prefix, cfg["id"], cfg["name"], cfg["area"]),
        ]:
            client.publish(topic, json.dumps(value), qos=1, retain=True)
        client.subscribe(prefix + "/command/+", qos=1)

    def message(client, userdata, msg):
        if msg.retain:
            return
        try:
            path, data = command(
                msg.topic.rsplit("/", 1)[-1], msg.payload.decode(), cfg["location_id"]
            )
            request(path, data)
        except Exception:
            print("Companion command failed; no retry", flush=True)

    client.on_connect = connected
    client.on_message = message
    client.max_queued_messages_set(16)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.connect_async(cfg["host"], cfg.get("port", 1883), 30)
    client.loop_start()
    try:
        while not stop.is_set():
            if not client.is_connected():
                stop.wait(1)
                continue
            try:
                state = request("/state")
                # Explicit projection: no inbox, transcript, calendar, tokens or preferences.
                value = {key: state[key] for key in ("character", "busy", "recording")}
                value["status"] = (
                    "recording" if value["recording"] else ("busy" if value["busy"] else "idle")
                )
                greeting = state.get("camera_greeting", {})
                sensors = greeting.get("sensors", {})
                for key in ("distance_mm", "temperature_c", "humidity_percent", "tilt_closed"):
                    value[key] = sensors.get(key)
                value["nearby"] = greeting.get("nearby")
                value["mac_screen"] = state.get("mac_screen", {}).get("state", "unknown")
                value["volume"] = state.get("speaker_volume", {}).get("percent")
                for role in ("voice", "display"):
                    value[role + "_connected"] = bool(
                        state.get("device_health", {}).get(role, {}).get("available")
                    )
                client.publish(prefix + "/state", json.dumps(value), qos=1, retain=False)
                client.publish(prefix + "/availability", "online", qos=1, retain=True)
            except Exception:
                client.publish(prefix + "/availability", "offline", qos=1, retain=True)
            stop.wait(15)
    finally:
        try:
            if client.is_connected():
                client.publish(
                    prefix + "/availability", "offline", qos=1, retain=True
                ).wait_for_publish(timeout=2)
        finally:
            client.disconnect()
            client.loop_stop()


def main():
    with stopping() as stop:
        run(stop)


if __name__ == "__main__":
    main()

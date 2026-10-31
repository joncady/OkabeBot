"""Read-only MQTT Discovery for a separate SSH-connected sensor satellite."""

import argparse
import json
import subprocess
from pathlib import Path

from .service_runtime import stopping
from .ha_companion import room_discovery

# Fixed diagnostic code, not supplied by MQTT or Home Assistant callers.
PROBE = """import json
from pathlib import Path
p=Path('/proc/net/wireless')
rows=p.read_text().splitlines() if p.exists() else []
signal=None
for row in rows:
    if 'wlan0:' in row:
        signal=float(row.split()[3].rstrip('.'))
t=Path('/sys/class/thermal/thermal_zone0/temp')
u=Path('/proc/uptime')
result={'connected':True,'wifi_signal':signal,
 'temperature':float(t.read_text())/1000 if t.exists() else None,
 'uptime':int(float(u.read_text().split()[0])) if u.exists() else None}
try:
 from urllib.request import Request, ProxyHandler, build_opener
 request=Request('http://127.0.0.1:8765/rpc',b'{"op":"room_sensors"}',
  {'Content-Type':'application/json'})
 with build_opener(ProxyHandler({})).open(request,timeout=2) as response:
  raw=response.read(16385)
 if len(raw)<=16384:
  room=json.loads(raw)
  if isinstance(room,dict) and room.get('connected') is True:
   result['room_sensors']=room
except Exception:
 pass
print(json.dumps(result))
"""


def room_values(value):
    """Project fresh optional readings; missing hardware is never false/zero."""
    raw = value.get("room_sensors", {})
    if not isinstance(raw, dict) or raw.get("connected") is not True:
        raw = {}
    result = {}
    for key, low, high in [
        ("distance_mm", 20, 4000),
        ("temperature_c", 0, 50),
        ("humidity_percent", 0, 100),
    ]:
        v = raw.get(key)
        types = (int,) if key == "distance_mm" else (int, float)
        result[key] = v if type(v) in types and low <= v <= high else None
    v = raw.get("button_pressed")
    result["button_pressed"] = v if type(v) is bool else None
    return result


def discovery(prefix, identity, name, area):
    device = {
        "identifiers": [identity],
        "name": name,
        "manufacturer": "OkabeBot",
        "model": "BLE observation satellite",
        "suggested_area": area,
    }
    for kind, key, label, extra in (
        (
            "binary_sensor",
            "connected",
            "SSH connected",
            {"device_class": "connectivity", "payload_on": True, "payload_off": False},
        ),
        (
            "sensor",
            "wifi_signal",
            "Wi-Fi signal",
            {
                "device_class": "signal_strength",
                "unit_of_measurement": "dBm",
                "state_class": "measurement",
            },
        ),
        (
            "sensor",
            "temperature",
            "CPU temperature",
            {
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "state_class": "measurement",
            },
        ),
        (
            "sensor",
            "uptime",
            "Uptime",
            {"device_class": "duration", "unit_of_measurement": "s", "state_class": "measurement"},
        ),
    ):
        config = {
            "name": label,
            "unique_id": identity + "_" + key,
            "device": device,
            "availability_topic": prefix + "/availability",
            "state_topic": prefix + "/state",
            "value_template": "{{ value_json." + key + " }}",
            **extra,
        }
        yield "homeassistant/" + kind + "/" + identity + "/" + key + "/config", config


def run(stop):
    import shlex
    from paho.mqtt import client as mqtt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    cfg = json.loads(parser.parse_args().config.read_text())
    prefix = "okabebot/" + cfg["id"]
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg["id"])
    client.username_pw_set(cfg["username"], cfg["password"])
    client.will_set(prefix + "/availability", "offline", qos=1, retain=True)

    def connected(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.publish(prefix + "/availability", "offline", qos=1, retain=True)
            for topic, config in discovery(prefix, cfg["id"], cfg["name"], cfg["area"]):
                client.publish(topic, json.dumps(config), qos=1, retain=True)

    client.on_connect = connected
    discovered_room = set()
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
                result = subprocess.run(
                    cfg["ssh_argv"] + ["python3 -c " + shlex.quote(PROBE)],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True,
                )
                value = json.loads(result.stdout)
                room = room_values(value)
                # Observe before advertising optional hardware. Re-publish to
                # recover broker discovery state; null packets keep it unavailable.
                discovered_room.update(k for k, v in room.items() if v is not None)
                for topic, config in room_discovery(
                    prefix, cfg["id"], cfg["name"], cfg["area"], fields=discovered_room
                ):
                    client.publish(topic, json.dumps(config), qos=1, retain=True)
                value.pop("room_sensors", None)
                value.update(room)
                client.publish(prefix + "/state", json.dumps(value), qos=1, retain=False)
                client.publish(prefix + "/availability", "online", qos=1, retain=True)
            except Exception:
                client.publish(prefix + "/availability", "offline", qos=1, retain=True)
            stop.wait(30)
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

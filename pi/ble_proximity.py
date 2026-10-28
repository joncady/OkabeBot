"""Bounded target-only BlueZ beacon scan; Python 3.7, no pairing or device actions."""

import argparse
from collections import deque
import json
import statistics
import sys
import time
import uuid


def beacon(data):
    raw = bytes(data)
    if len(raw) != 23 or raw[:2] != b"\x02\x15":
        return None
    return (
        str(uuid.UUID(bytes=raw[2:18])),
        int.from_bytes(raw[18:20], "big"),
        int.from_bytes(raw[20:22], "big"),
    )


class Gate:
    """RSSI is a proximity cue, not distance or proof of a person's location."""

    def __init__(self, enter=-60, exit=-75, dwell=4, lost=15, cooldown=120, sample_window=10):
        if (
            not -100 <= exit < enter <= -20
            or not 1 <= dwell <= 30
            or not 5 <= lost <= 60
            or not 30 <= cooldown <= 3600
            or not 5 <= sample_window <= 30
        ):
            raise ValueError("Invalid proximity thresholds")
        self.enter, self.exit, self.dwell, self.lost, self.cooldown = (
            enter,
            exit,
            dwell,
            lost,
            cooldown,
        )
        self.sample_window = sample_window
        self.samples = deque()
        self.since = None
        self.last_seen = None
        self.last_near = None
        self.state = "unknown"

    def update(self, now, rssi=None):
        if self.last_seen is not None and now - self.last_seen > self.lost:
            self.samples.clear()
            self.since = None
            self.state = "unknown"
        if rssi is not None:
            if type(rssi) not in (int, float) or not -127 <= rssi <= 0:
                return None
            self.last_seen = now
            self.samples.append((now, rssi))
        while self.samples and now - self.samples[0][0] > self.sample_window:
            self.samples.popleft()
        if not self.samples:
            self.since = None
            return None
        strength = statistics.median(v for _, v in self.samples)
        if strength <= self.exit:
            self.state, self.since = "far", None
        elif strength < self.enter:
            self.since = None
        elif self.state != "near":
            if self.since is None:
                self.since = now
            if len(self.samples) >= 3 and now - self.since >= self.dwell:
                self.state = "near"
                if self.last_near is None or now - self.last_near >= self.cooldown:
                    self.last_near = now
                    return "near"
        return None


def scan(settings, seconds):
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    target = (str(uuid.UUID(settings["uuid"])), int(settings["major"]), int(settings["minor"]))
    if any(not 0 <= n <= 65535 for n in target[1:]):
        raise ValueError("Invalid beacon identity")
    gate = Gate(
        **{
            k: settings[k]
            for k in ("enter", "exit", "dwell", "lost", "cooldown", "sample_window")
            if k in settings
        }
    )
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
    objects = manager.GetManagedObjects()
    adapters = [
        path
        for path, props in objects.items()
        if "org.bluez.Adapter1" in props and props["org.bluez.Adapter1"].get("Powered")
    ]
    requested = settings.get("adapter", "hci0")
    path = next((p for p in adapters if str(p).endswith("/" + requested)), None)
    if path is None:
        raise ValueError("Configured BLE adapter unavailable")
    adapter = dbus.Interface(bus.get_object("org.bluez", path), "org.bluez.Adapter1")
    cache = {}
    loop = GLib.MainLoop()
    matched = [False]

    def emit(value):
        print(json.dumps(value), flush=True)

    def inspect(device_path, changes):
        if not str(device_path).startswith(str(path) + "/"):
            return
        props = cache.setdefault(device_path, {})
        props.update(changes)
        manufacturer = props.get("ManufacturerData", {})
        identity = beacon(manufacturer.get(76, b""))
        if identity != target or "RSSI" not in props:
            return
        if "RSSI" not in changes and "ManufacturerData" not in changes:
            return
        if not matched[0]:
            matched[0] = True
            emit({"state": "target_seen"})
        strength = int(props["RSSI"])
        event = gate.update(time.monotonic(), strength)
        emit({"state": event or "sample", "rssi": strength})

    def changed(interface, changes, invalidated, path=None):
        if interface == "org.bluez.Device1":
            inspect(path, changes)

    def added(device_path, interfaces):
        if "org.bluez.Device1" in interfaces:
            inspect(device_path, interfaces["org.bluez.Device1"])

    for device_path, props in objects.items():
        if "org.bluez.Device1" in props:
            cache[device_path] = dict(props["org.bluez.Device1"])
    bus.add_signal_receiver(
        changed,
        dbus_interface="org.freedesktop.DBus.Properties",
        signal_name="PropertiesChanged",
        path_keyword="path",
    )
    bus.add_signal_receiver(
        added, dbus_interface="org.freedesktop.DBus.ObjectManager", signal_name="InterfacesAdded"
    )
    adapter.SetDiscoveryFilter(
        dbus.Dictionary({"Transport": "le", "DuplicateData": True}, signature="sv")
    )
    started = False
    try:
        adapter.StartDiscovery()
        started = True
        emit({"state": "scanning"})
        GLib.timeout_add_seconds(seconds, lambda: (loop.quit(), False)[1])

        def tick():
            event = gate.update(time.monotonic())
            if event:
                emit({"state": event})
            return True

        GLib.timeout_add_seconds(1, tick)
        loop.run()
    finally:
        if started:
            adapter.StopDiscovery()
        emit({"state": "stopped"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 900:
        parser.error("Use a bounded 5–900 second scan")
    # Identity arrives over SSH stdin, never a process argument or scan log.
    scan(json.load(sys.stdin), args.seconds)


if __name__ == "__main__":
    main()

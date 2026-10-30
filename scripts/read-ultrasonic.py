#!/usr/bin/env python3
"""Bounded local serial diagnostic for the Uno distance reader (Mac/Linux)."""

import argparse
import json
import os
import select
import termios
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", required=True, help="Exact serial device, e.g. /dev/cu.usbmodem…")
parser.add_argument("--seconds", type=int, default=8, choices=range(1, 61))
args = parser.parse_args()
fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
original = termios.tcgetattr(fd)
try:
    config = termios.tcgetattr(fd)
    config[0] = config[1] = config[3] = 0
    config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    config[4] = config[5] = termios.B115200
    config[6][termios.VMIN] = 0
    config[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, config)
    termios.tcflush(fd, termios.TCIFLUSH)
    end, buffer = time.monotonic() + args.seconds, b""
    while time.monotonic() < end:
        if not select.select([fd], [], [], min(0.5, max(0, end - time.monotonic())))[0]:
            continue
        raw = os.read(fd, 1024)
        if not raw:
            raise RuntimeError("Serial device disconnected")
        buffer += raw
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            try:
                value = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(value, dict) or value.get("sensor") not in ("ultrasonic", "room"):
                continue
            if value["sensor"] == "room":
                light, tilt = value.get("light_raw"), value.get("tilt_closed")
                if (light is None or type(light) is int and 0 <= light <= 1023) and type(
                    tilt
                ) is bool:
                    print(json.dumps(value), flush=True)
                continue
            distance = value.get("distance_mm")
            if distance is None or type(distance) is int and 20 <= distance <= 4000:
                print(json.dumps(value), flush=True)
        if len(buffer) > 4096:
            buffer = b""
finally:
    termios.tcsetattr(fd, termios.TCSANOW, original)
    os.close(fd)

"""Python 3.7 USB Uno reader; bounded, volatile samples and reconnect handling."""

import json
import os
import select
import termios
import threading
import time


class Samples:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.values = {}

    def accept(self, value):
        if not isinstance(value, dict):
            return
        kind = value.get("sensor")
        clean = {}
        if kind == "ultrasonic":
            distance = value.get("distance_mm")
            if distance is not None and (type(distance) is not int or not 20 <= distance <= 4000):
                return
            clean = {"distance_mm": distance}
        elif kind == "room":
            for key, low, high in [("temperature_c", 0, 50), ("humidity_percent", 0, 100)]:
                v = value.get(key)
                if v is not None and (type(v) not in (int, float) or not low <= v <= high):
                    return
                clean[key] = v
            if type(value.get("tilt_closed")) is not bool:
                return
            clean["tilt_closed"] = value["tilt_closed"]
        else:
            return
        with self.lock:
            self.values[kind] = (self.clock(), clean)

    def snapshot(self):
        now = self.clock()
        result = {
            "distance_mm": None,
            "temperature_c": None,
            "humidity_percent": None,
            "tilt_closed": None,
            "connected": False,
        }
        with self.lock:
            for stamp, value in self.values.values():
                if 0 <= now - stamp <= 6:
                    result.update(value)
                    result["connected"] = True
        return result

    def clear(self):
        with self.lock:
            self.values.clear()


class Reader(Samples):
    def __init__(self, port):
        super().__init__()
        self.port = port
        if port:
            threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            fd = None
            try:
                fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                attrs = termios.tcgetattr(fd)
                attrs[0] = attrs[1] = attrs[3] = 0
                attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
                attrs[4] = attrs[5] = termios.B115200
                attrs[6][termios.VMIN] = 0
                attrs[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
                termios.tcflush(fd, termios.TCIFLUSH)
                buffer = b""
                while True:
                    if not select.select([fd], [], [], 1)[0]:
                        continue
                    raw = os.read(fd, 1024)
                    if not raw:
                        raise OSError("Serial disconnected")
                    buffer += raw
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        try:
                            self.accept(json.loads(line))
                        except (ValueError, UnicodeError):
                            pass
                    if len(buffer) > 4096:
                        buffer = b""
            except (OSError, termios.error):
                self.clear()
            finally:
                if fd is not None:
                    os.close(fd)
            time.sleep(3)

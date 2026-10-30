"""Apply kiosk power settings only after Tk has opened its X11 display. Python 3.7."""

import subprocess


def keep_awake(display, enabled=True):
    if not enabled:
        return True
    success = True
    for arguments in (("dpms", "force", "on"), ("-dpms",), ("s", "off"), ("s", "noblank")):
        try:
            result = subprocess.run(
                ["xset", "-display", display] + list(arguments),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            success = result.returncode == 0 and success
        except (OSError, subprocess.SubprocessError):
            success = False
    return success


class Power:
    """UTC intervals survive controller restarts; never stops audio/sensor services."""

    def __init__(self, display, path, clock=None, run=None):
        import time
        import json
        from pathlib import Path

        self.display, self.path = display, Path(path)
        self.clock, self.run = clock or time.time, run or subprocess.run
        self.intervals, self.wake_minutes = [], 5
        self.override_until = 0
        self.awake = None
        self.backend = None
        self.error = None
        self.next_attempt = 0
        self.last_wanted = None
        try:
            value = json.loads(self.path.read_text())
            value["intervals"] = [p for p in value["intervals"] if p[1] > self.clock()]
            self.set_schedule(value, save=False)
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            pass

    def set_schedule(self, value, save=True):
        import math
        import json
        import os
        import tempfile

        spans = value.get("intervals")
        minutes = value.get("wake_minutes")
        now = self.clock()
        if (
            not isinstance(spans, list)
            or len(spans) > 10
            or type(minutes) is not int
            or not 1 <= minutes <= 60
        ):
            raise ValueError("Invalid display schedule")
        for pair in spans:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or any(type(n) not in (int, float) or not math.isfinite(n) for n in pair)
                or not now - 2 * 86400 <= pair[0] < pair[1] <= now + 10 * 86400
            ):
                raise ValueError("Invalid bounded display interval")
        changed = spans != self.intervals or minutes != self.wake_minutes
        self.intervals, self.wake_minutes = spans, minutes
        if save and changed:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=str(self.path.parent), delete=False
            ) as f:
                json.dump({"intervals": spans, "wake_minutes": minutes}, f)
                name = f.name
            os.replace(name, str(self.path))

    def wake(self):
        self.override_until = self.clock() + self.wake_minutes * 60
        return self.tick()

    def switch(self, awake):
        # Legacy Pi framebuffer HDMI power is separate from X11's idle timer.
        try:
            query = self.run(
                ["vcgencmd", "display_power"], capture_output=True, text=True, timeout=3
            )
            if query.returncode == 0 and "display_power=" in query.stdout:
                result = self.run(
                    ["vcgencmd", "display_power", "1" if awake else "0"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if (
                    result.returncode == 0
                    and ("display_power=" + ("1" if awake else "0")) in result.stdout
                ):
                    self.backend = "firmware"
                    return True
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            self.run(["xset", "-display", self.display, "+dpms"], capture_output=True, timeout=3)
            self.run(
                ["xset", "-display", self.display, "dpms", "0", "0", "0"],
                capture_output=True,
                timeout=3,
            )
            result = self.run(
                ["xset", "-display", self.display, "dpms", "force", "on" if awake else "off"],
                capture_output=True,
                timeout=3,
            )
            if result.returncode == 0:
                self.backend = "dpms"
                return True
        except (OSError, subprocess.SubprocessError):
            pass
        return False

    def tick(self):
        now = self.clock()
        wanted = now < self.override_until or not any(a <= now < b for a, b in self.intervals)
        if wanted != self.awake and (wanted != self.last_wanted or now >= self.next_attempt):
            self.last_wanted = wanted
            self.next_attempt = now + 30
            if self.switch(wanted):
                self.awake, self.error = wanted, None
            else:
                self.error = "Display power command unavailable"
        return {
            "awake": self.awake,
            "backend": self.backend,
            "error": self.error,
            "override_until": self.override_until,
        }

    def command(self, data):
        action = data.get("action")
        if action == "schedule" and set(data) == {"op", "action", "intervals", "wake_minutes"}:
            self.set_schedule(data)
            return self.tick()
        if action == "wake" and set(data) == {"op", "action"}:
            return self.wake()
        raise ValueError("Unsupported display power command")

"""Owner-configured night schedule; send timezone-resolved intervals to a Pi."""

from datetime import datetime, timedelta
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from threading import RLock
from .presence_control import read, write

DEFAULTS = {
    "enabled": False,
    "sleep_start": "22:00",
    "sleep_end": "08:00",
    "timezone": "UTC",
    "wake_minutes": 5,
}


def validate(data):
    if (
        not isinstance(data, dict)
        or set(data) != set(DEFAULTS)
        or type(data["enabled"]) is not bool
    ):
        raise ValueError("Use the screen night-mode settings")
    for key in ("sleep_start", "sleep_end"):
        if not isinstance(data[key], str) or not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", data[key]
        ):
            raise ValueError("Use HH:MM night times")
    if not isinstance(data["timezone"], str):
        raise ValueError("Choose an IANA timezone")
    try:
        ZoneInfo(data["timezone"])
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Choose an IANA timezone") from None
    if type(data["wake_minutes"]) is not int or not 1 <= data["wake_minutes"] <= 60:
        raise ValueError("Wake duration must be 1–60 minutes")
    return dict(data)


def intervals(cfg, now):
    if not cfg["enabled"]:
        return []
    zone = ZoneInfo(cfg["timezone"])
    day = datetime.fromtimestamp(now, zone).date()
    start_h, start_m = map(int, cfg["sleep_start"].split(":"))
    end_h, end_m = map(int, cfg["sleep_end"].split(":"))
    result = []
    for n in range(-1, 8):
        date = day + timedelta(days=n)
        start = datetime(date.year, date.month, date.day, start_h, start_m, tzinfo=zone)
        end = datetime(date.year, date.month, date.day, end_h, end_m, tzinfo=zone)
        if end <= start:
            end += timedelta(days=1)
        if end.timestamp() > now:
            result.append([start.timestamp(), end.timestamp()])
    return result


class ScreenPower:
    def __init__(self, folder, rpc, clock=time.time):
        self.path = Path(folder) / "screen-power.json"
        self.rpc, self.clock = rpc, clock
        self.lock = RLock()
        self.next_check = 0
        self.health = {"state": "waiting"}

    def snapshot(self):
        return {"config": {**DEFAULTS, **read(self.path, {})}, **self.health}

    def configure(self, data):
        with self.lock:
            write(self.path, validate(data))
            self.next_check = 0
            self.tick()
            return self.snapshot()

    def tick(self):
        with self.lock:
            return self._tick()

    def _tick(self):
        now = self.clock()
        if now < self.next_check:
            return
        self.next_check = now + 30
        cfg = self.snapshot()["config"]
        try:
            result = self.rpc(
                {
                    "op": "screen_power",
                    "action": "schedule",
                    "intervals": intervals(cfg, now),
                    "wake_minutes": cfg["wake_minutes"],
                }
            )
            self.health = (
                {"state": "unavailable"}
                if result.get("error")
                else {"state": "connected", "display": result}
            )
        except Exception:
            self.health = {"state": "unavailable"}

    def wake(self):
        result = self.rpc({"op": "screen_power", "action": "wake"})
        if result.get("error"):
            raise ValueError("Display wake unavailable")
        self.health = {"state": "connected", "display": result}
        return self.snapshot()

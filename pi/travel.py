"""Leased character presence and simple walking transforms. Python 3.7."""

import math
import re
import time
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont


class Motion:
    def __init__(self):
        self.phase = "home"
        self.identifier = ""
        self.started = 0
        self.duration = 1.4
        self.direction = "left"
        self.lease = 0
        self.command_key = None
        self.rendered = "home"
        self.from_x = 0

    def command(self, data, now=None):
        now = time.monotonic() if now is None else now
        identifier, phase = data.get("transition_id", ""), data.get("phase")
        duration, lease = data.get("duration_seconds", 1.4), data.get("lease_seconds", 12)
        if not re.fullmatch(r"[a-f0-9]{32}", identifier) or phase not in (
            "departing",
            "away",
            "arriving",
            "home",
        ):
            raise ValueError("Invalid travel command")
        if data.get("direction", "left") not in ("left", "right", "up", "down"):
            raise ValueError("Invalid travel direction")
        if type(duration) not in (int, float) or not 0.5 <= duration <= 5:
            raise ValueError("Travel duration must be 0.5–5 seconds")
        if type(lease) not in (int, float) or not 8 <= lease <= 30:
            raise ValueError("Travel lease must be 8–30 seconds")
        key = (identifier, phase)
        if key != self.command_key:
            _, dx, dy = self.sample(now)
            self.from_x = dy if self.direction in ("up", "down") else dx
            self.identifier, self.phase, self.started = identifier, phase, now
            self.direction, self.duration, self.command_key = (
                data.get("direction", "left"),
                duration,
                key,
            )
        self.lease = now + lease
        return self.status()

    def sample(self, now=None):
        now = time.monotonic() if now is None else now
        distance = -520 if self.direction in ("left", "up") else 520
        progress = min(1, max(0, (now - self.started) / self.duration))
        ease = progress * progress * (3 - 2 * progress)
        if self.phase in ("away", "departing") and now > self.lease:
            self.from_x = (
                distance if self.phase == "away" else self.from_x + (distance - self.from_x) * ease
            )
            self.phase, self.started, progress, ease = "arriving", now, 0, 0
        if self.phase == "departing" and progress >= 1:
            self.phase = "away"
        elif self.phase == "arriving" and progress >= 1:
            self.phase = "home"
        dx = (
            self.from_x + (distance - self.from_x) * ease
            if self.phase == "departing"
            else self.from_x * (1 - ease)
            if self.phase == "arriving"
            else distance
            if self.phase == "away"
            else 0
        )
        bob = (
            -abs(math.sin(progress * math.pi * 7)) * 4
            if self.phase in ("departing", "arriving")
            else 0
        )
        return (
            (self.phase, 0, dx + bob) if self.direction in ("up", "down") else (self.phase, dx, bob)
        )

    def status(self):
        return {"phase": self.phase, "rendered": self.rendered, "transition_id": self.identifier}


def shifted(shapes, dx, dy):
    return [shapes[0]] + [
        (kind, tuple(v + (dx if i % 2 == 0 else dy) for i, v in enumerate(xy)), color, width)
        for kind, xy, color, width in shapes[1:]
    ]


@lru_cache(maxsize=4)
def sign(background="#101e25"):
    im = Image.new("RGB", (480, 320), background)
    d = ImageDraw.Draw(im)
    d.ellipse((110, 279, 370, 298), fill="#081218")
    d.rectangle((221, 216, 239, 285), fill="#927459")
    d.rectangle((241, 216, 255, 285), fill="#624f43")
    d.rectangle((41, 68, 439, 232), fill="#7b6552")
    d.rectangle((48, 75, 432, 225), fill="#d6c3a2")
    d.rectangle((56, 83, 424, 217), fill="#20383e")

    def font(size):
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()

    d.text((84, 108), "BE BACK SOON", font=font(29), fill="#f4e6c8")
    d.text((94, 158), "Taking up more pixels.", font=font(19), fill="#a5d7c8")
    d.polygon(((22, 149), (35, 137), (35, 161)), fill="#a5d7c8")
    return im

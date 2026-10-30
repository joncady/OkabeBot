"""Silent, bounded focus projection. Python 3.7; no persistence or transport."""

import math
import time

from PIL import Image, ImageDraw, ImageFont

BADGE_POSITION = (368, 8)


class Focus:
    def __init__(self):
        self.ends_at = None

    def command(self, data, now=None):
        now = time.time() if now is None else now
        if not isinstance(data, dict) or set(data) != {"op", "active", "ends_at"}:
            raise ValueError("Use focus active and end time")
        if data["op"] != "focus" or type(data["active"]) is not bool:
            raise ValueError("Invalid focus state")
        end = data["ends_at"]
        if data["active"]:
            if (
                type(end) not in (int, float)
                or not math.isfinite(end)
                or not -5 <= end - now <= 10860
            ):
                raise ValueError("Focus end must be within three hours; check clocks")
            self.ends_at = end
        elif end is not None:
            raise ValueError("Inactive focus must have no end time")
        else:
            self.ends_at = None
        return self.status(now)

    def status(self, now=None):
        now = time.time() if now is None else now
        remaining = max(0, int(math.ceil(self.ends_at - now))) if self.ends_at else 0
        return {
            "active": remaining > 0,
            "ends_at": self.ends_at if remaining else None,
            "remaining_seconds": remaining,
        }

    def quiet_args(self, args, blocked=False, now=None):
        if (
            blocked
            or args.get("activity") != "idle"
            or args.get("gesture") not in (None, "idle")
            or not self.status(now)["active"]
        ):
            return args
        return dict(
            args,
            emotion="neutral",
            intensity=min(args.get("intensity", 0.6), 0.2),
            mouth=0,
            idle_seconds=0,
            gesture="idle",
            phase=args.get("phase", 0) * 0.25,
        )


def visible(active, character, phase="home", notification=None, music=None, deploying=False):
    """Higher-priority presentation always keeps its original space and expression."""
    music = music or {}
    return bool(
        active
        and character
        and character.get("activity") == "idle"
        and phase == "home"
        and not notification
        and not music.get("is_playing")
        and not music.get("video")
        and not deploying
    )


def badge(seconds):
    """Pixel hourglass and countdown; one small top-corner overlay, never a card."""
    seconds = max(0, int(seconds))
    image = Image.new("RGBA", (52, 16))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 0, 50, 15), fill="#172b34")
    draw.rectangle((0, 1, 51, 14), fill="#172b34")
    draw.line((2, 0, 49, 0), fill="#789b99")
    draw.line((2, 15, 49, 15), fill="#42635f")
    # Tiny pixel hourglass, static rather than a flashing loading indicator.
    draw.line((5, 4, 11, 4), fill="#9ac5bb")
    draw.line((5, 11, 11, 11), fill="#9ac5bb")
    draw.line((6, 5, 10, 10), fill="#9ac5bb")
    draw.line((10, 5, 6, 10), fill="#9ac5bb")
    draw.text(
        (15, 3),
        "{}:{:02d}".format(seconds // 60, seconds % 60),
        font=ImageFont.load_default(),
        fill="#c2d9cf",
    )
    return image.resize((104, 32), Image.NEAREST)


def overlay(image, status, show):
    if not show or not status.get("active"):
        return image
    result = image.convert("RGBA")
    result.alpha_composite(badge(status["remaining_seconds"]), BADGE_POSITION)
    return result

"""Content reaction vocabulary. Python 3.7; no metadata parsing or network access."""

import math
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

try:
    from . import prop_art
except ImportError:
    import prop_art

EMOTIONS = {
    "attentive": "neutral",
    "engaged": "curious",
    "amused": "happy",
    "tense": "concerned",
    "wonder": "excited",
    "curious": "curious",
    "moved": "happy",
    "delighted": "happy",
    "upbeat": "happy",
    "calm": "neutral",
    "competitive": "excited",
    "analytical": "curious",
    "energetic": "excited",
    "serious": "neutral",
}


def active(music, notification=None, activity="idle", deploying=False):
    video = (music or {}).get("video") or {}
    return bool(
        video
        and video.get("state") in ("PLAYING", "PAUSED", "BUFFERING")
        and not notification
        and activity == "idle"
        and not deploying
    )


def move(shapes, reaction, phase, state):
    if state != "PLAYING":
        return shapes
    mode = reaction.get("reaction", "attentive")
    strength = 0.4 + reaction.get("energy", 0.4)
    tilt = math.sin(phase * (2.2 if mode in ("competitive", "energetic", "upbeat") else 0.7))
    tilt *= (0.045 if mode in ("amused", "upbeat", "competitive") else 0.018) * strength
    bob = abs(math.sin(phase * 2)) * 3 * strength if mode in ("amused", "energetic") else 0
    if mode == "calm":
        tilt *= 0.3
    result = [shapes[0]]
    for kind, coords, color, width in shapes[1:]:
        if kind == "rectangle":
            x, y, xx, yy = coords
            coords = (x, y, xx, y, xx, yy, x, yy)
            kind = "polygon"
        out = []
        for i in range(0, len(coords), 2):
            x, y = coords[i : i + 2]
            weight = max(0, min(1, (220 - y) / 130))
            out.extend(
                (x + (180 - y) * tilt * weight, y + (x - 240) * tilt * weight + bob * weight)
            )
        result.append((kind, tuple(out), color, width))
    return result


@lru_cache(maxsize=64)
def badge(crest, label, colors):
    path = Path(__file__).resolve().parent / "assets" / "crests" / (crest + ".png")
    if crest and all(c.isalnum() or c in "_-" for c in crest) and path.is_file():
        with Image.open(str(path)) as im:
            crest_image = im.convert("RGBA")
            crest_image.thumbnail((40, 40), Image.NEAREST)
            canvas = Image.new("RGBA", (40, 40))
            canvas.alpha_composite(
                crest_image, ((40 - crest_image.width) // 2, (40 - crest_image.height) // 2)
            )
            return canvas
    im = Image.new("RGBA", (40, 40))
    d = ImageDraw.Draw(im)
    d.polygon([(2, 1), (37, 1), (37, 25), (20, 38), (2, 25)], fill=colors[0])
    d.rectangle((5, 9, 34, 27), fill=colors[1])
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 10)
    except OSError:
        f = ImageFont.load_default()
    w = f.getlength(label[:5]) if hasattr(f, "getlength") else d.textsize(label[:5], font=f)[0]
    d.text(((40 - w) // 2, 12), label[:5], fill="#101e25", font=f)
    return im


@lru_cache(maxsize=64)
def badge_runs(crest, label, colors):
    im = badge(crest, label, colors)
    runs = []
    for y in range(40):
        x = 0
        while x < 40:
            color = im.getpixel((x, y))
            end = x + 1
            while end < 40 and im.getpixel((end, y)) == color:
                end += 1
            if color[3] > 127:
                runs.append((x, y, end, "#%02x%02x%02x" % color[:3]))
            x = end
    return tuple(runs)


@lru_cache(maxsize=4)
def soccer_sprite(frame):
    """Four rolling 16x16 frames with stable cells for retained-canvas drawing."""
    rows = []
    for y in range(16):
        pixels = []
        for x in range(16):
            radius = (x - 7.5) ** 2 + (y - 7.5) ** 2
            if radius > 61:
                color = None
            elif radius > 48:
                color = "#26343b"
            else:
                patch_x = (x + frame * 3) % 12
                dark = (
                    (5 <= y <= 9 and 4 <= patch_x <= 7)
                    or (y < 4 and 0 <= patch_x <= 2)
                    or (y > 11 and 9 <= patch_x <= 11)
                )
                color = "#26343b" if dark else ("#c6d1cd" if y > 10 else "#f4f1e8")
            pixels.append(color)
        for x, color in enumerate(pixels):
            if color:
                rows.append((x, y, x + 1, color))
    return tuple(rows)


def decorations(reaction, phase, state, native_sprites=False):
    out = []

    def add(kind, xy, color, width=1):
        out.append((kind, xy, color, width))

    phase = phase if state == "PLAYING" else 0
    teams = [] if native_sprites else reaction.get("participants", [])[:2]
    for i, team in enumerate(teams):
        for x, y, end, color in badge_runs(
            team.get("crest", ""),
            team.get("short_name", "?"),
            tuple(team.get("colors", ["#486a81", "#ffffff"])),
        ):
            # 64px crests retain their existing side centers.
            add(
                "rectangle",
                (
                    18 + i * 380 + x * 1.6,
                    80 + y * 1.6,
                    18 + i * 380 + end * 1.6,
                    80 + (y + 1) * 1.6,
                ),
                color,
            )
    if prop_art.available():
        if not native_sprites:
            out.extend(prop_art.shapes(reaction, phase, state))
        return out
    prop = reaction.get("prop", "screen")
    x, y = 74, 175 + math.sin(phase * 1.2) * 3
    if prop == "ball":
        sport = reaction.get("sport")
        if sport == "soccer":
            if native_sprites:
                return out
            bounce = round(abs(math.sin(phase * 2.8)) * 6)
            add("rectangle", (54, 265, 94, 268), "#09151b")
            for px, py, end, color in soccer_sprite(int(phase * 6) % 4):
                add(
                    "rectangle",
                    (
                        50 + px * 3,
                        216 - bounce + py * 3,
                        50 + end * 3 - 1,
                        216 - bounce + (py + 1) * 3 - 1,
                    ),
                    color,
                )
            return out
        if sport == "american_football" or sport == "rugby":
            add("ellipse", (x - 20, y - 12, x + 20, y + 12), "#a86438")
            add("line", (x - 10, y, x + 10, y), "#ffffff", 2)
            for n in range(-6, 7, 6):
                add("line", (x + n, y - 4, x + n, y + 4), "#ffffff", 2)
        else:
            add("ellipse", (x - 16, y - 16, x + 16, y + 16), "#f4f1e8")
            if sport == "basketball":
                out[-1] = ("ellipse", (x - 16, y - 16, x + 16, y + 16), "#ef963e", 1)
                add("line", (x - 16, y, x + 16, y), "#493724", 2)
                add("line", (x, y - 16, x, y + 16), "#493724", 2)
            elif sport == "soccer":
                add(
                    "polygon",
                    (x, y - 8, x + 8, y - 2, x + 5, y + 7, x - 5, y + 7, x - 8, y - 2),
                    "#26343b",
                )
    elif prop == "heart":
        add("ellipse", (x - 15, y - 12, x + 1, y + 4), "#ec849a")
        add("ellipse", (x - 1, y - 12, x + 15, y + 4), "#ec849a")
        add("polygon", (x - 15, y - 3, x + 15, y - 3, x, y + 17), "#ec849a")
    elif prop in ("star", "spark"):
        add(
            "polygon",
            (
                x,
                y - 18,
                x + 5,
                y - 5,
                x + 18,
                y,
                x + 5,
                y + 5,
                x,
                y + 18,
                x - 5,
                y + 5,
                x - 18,
                y,
                x - 5,
                y - 5,
            ),
            "#f2cb70",
        )
    elif prop == "controller":
        add(
            "polygon",
            (
                x - 18,
                y - 10,
                x + 18,
                y - 10,
                x + 24,
                y + 12,
                x + 12,
                y + 16,
                x + 6,
                y + 5,
                x - 6,
                y + 5,
                x - 12,
                y + 16,
                x - 24,
                y + 12,
            ),
            "#a8d9cd",
        )
        add("line", (x - 15, y, x - 5, y), "#26343b", 3)
        add("line", (x - 10, y - 5, x - 10, y + 5), "#26343b", 3)
        add("ellipse", (x + 9, y - 3, x + 13, y + 1), "#df6a73")
    elif prop == "book":
        add(
            "polygon",
            (x - 20, y - 14, x, y - 8, x + 20, y - 14, x + 20, y + 14, x, y + 20, x - 20, y + 14),
            "#d9e6db",
        )
        add("line", (x, y - 8, x, y + 20), "#6a9d8d", 2)
    elif prop in ("search", "compass"):
        add("ellipse", (x - 15, y - 15, x + 10, y + 10), "#a8d9cd")
        add("ellipse", (x - 11, y - 11, x + 6, y + 6), "#172b34")
        add("line", (x + 6, y + 6, x + 19, y + 19), "#a8d9cd", 5)
    elif prop in ("planet", "moon"):
        add("ellipse", (x - 15, y - 15, x + 15, y + 15), "#b49fd3")
        if prop == "planet":
            add("line", (x - 24, y + 9, x + 24, y - 9), "#c7d7e1", 3)
        else:
            add("ellipse", (x - 6, y - 18, x + 21, y + 7), "#101e25")
    elif prop == "note":
        add("ellipse", (x - 12, y + 8, x, y + 17), "#a8d9cd")
        add("line", (x, y + 12, x, y - 18, x + 15, y - 12), "#a8d9cd", 4)
    else:
        # Reusable context token for formats awaiting bespoke artwork.
        add("rectangle", (x - 21, y - 15, x + 21, y + 15), "#668d9b")
        add("rectangle", (x - 17, y - 11, x + 17, y + 11), "#172b34")
        add("polygon", (x - 5, y - 7, x + 8, y, x - 5, y + 7), "#a8d9cd")
    # Quiet secondary accent on opposite side when no second team is supplied.
    if len(teams) < 2:
        add("ellipse", (398, 168, 404, 174), "#668d9b")
    return out

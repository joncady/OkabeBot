"""Character presentation composition; no transport, clocks or hardware. Python 3.7."""

import math
import time
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

try:
    from . import pip_face, reactions
except ImportError:
    import pip_face
    import reactions


@lru_cache(maxsize=1)
def media_aliases():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent
    path = root / "media-apps.local.json"
    if not path.exists():
        path = root / "assets/media-apps.json"
    try:
        aliases = json.loads(path.read_text()).get("aliases", {})
    except (OSError, ValueError, AttributeError):
        aliases = {}
    return aliases


def media_source(app):
    return media_aliases().get("".join(str(app).casefold().split()), "tv")


@lru_cache(maxsize=32)
def icon(source, size=32):
    # Optional Wikipedia-sourced assets are downloaded on the controller,
    # never fetched on the Pi's render loop. Unknown/missing assets use pixel icons.
    from pathlib import Path

    if str(source).isalnum():
        path = Path(__file__).resolve().parent / "assets/app-logos" / (source + ".png")
        try:
            with Image.open(str(path)) as logo:
                logo = logo.convert("RGBA")
                logo.thumbnail((size, size), Image.NEAREST)
                canvas = Image.new("RGBA", (size, size))
                canvas.alpha_composite(logo, ((size - logo.width) // 2, (size - logo.height) // 2))
                return canvas
        except (OSError, ValueError):
            pass
    image = Image.new("RGBA", (16, 16))
    d = ImageDraw.Draw(image)
    if str(source).lower() == "youtube":
        d.rectangle((2, 3, 13, 12), fill="#ff3030")
        d.rectangle((1, 4, 14, 11), fill="#ff3030")
        d.polygon([(6, 5), (6, 11), (11, 8)], fill="#ffffff")
    elif source == "spotify":
        d.ellipse((0, 0, 15, 15), fill="#1ed760")
        for y, right in ((4, 12), (7, 11), (10, 10)):
            d.line([(3, y + 1), (6, y), (9, y), (right, y + 1)], fill="#10231a", width=1)
    elif source == "prime":
        d.rectangle((0, 0, 15, 15), fill="#00a8e1")
        # Pixel P and Amazon's smile, legible at the screen's small icon size.
        d.line([(4, 9), (4, 2), (9, 2), (10, 3), (10, 5), (9, 6), (4, 6)], fill="white", width=2)
        d.line([(3, 11), (5, 13), (10, 13), (13, 10)], fill="white", width=1)
        d.line([(10, 10), (13, 10), (13, 13)], fill="white", width=1)
    elif source == "max":
        d.rectangle((0, 0, 15, 15), fill="#1236ea")
        d.line([(3, 12), (3, 4), (7, 8), (11, 4), (11, 12)], fill="white", width=2)
    elif source == "netflix":
        d.rectangle((0, 0, 15, 15), fill="#101010")
        d.rectangle((3, 2, 5, 13), fill="#b20710")
        d.rectangle((10, 2, 12, 13), fill="#b20710")
        d.polygon([(3, 2), (6, 2), (12, 13), (9, 13)], fill="#e50914")
    elif source == "fubo":
        d.rectangle((0, 0, 15, 15), fill="#f56b2a")
        d.line([(5, 12), (5, 3), (12, 3)], fill="white", width=2)
        d.line([(5, 7), (10, 7)], fill="white", width=2)
    elif source == "disney":
        d.rectangle((0, 0, 15, 15), fill="#1534a2")
        d.arc((1, 1, 14, 14), 190, 340, fill="#8fd9ff", width=1)
        d.line(
            [(5, 12), (5, 5), (9, 5), (11, 7), (11, 10), (9, 12), (5, 12)], fill="white", width=1
        )
    elif source == "tv":
        d.rectangle((1, 2, 14, 12), outline="#a8d9cd")
        d.rectangle((6, 13, 9, 14), fill="#a8d9cd")
    elif source == "github":
        d.rectangle((2, 3, 13, 12), fill="#ede8e0")
        d.polygon([(2, 5), (2, 1), (6, 3), (10, 3), (13, 1), (13, 6)], fill="#ede8e0")
        d.rectangle((5, 7, 10, 10), fill="#24363c")
        d.rectangle((6, 12, 9, 15), fill="#ede8e0")
        d.line((6, 13, 3, 13, 1, 10), fill="#ede8e0", width=2)
    elif source == "calendar":
        d.rectangle((1, 2, 14, 14), fill="#f5eee2")
        d.rectangle((1, 2, 14, 5), fill="#e9a176")
        for x in (4, 10):
            d.rectangle((x, 0, x + 1, 3), fill="#faf5ec")
        for x in (4, 7, 10):
            for y in (8, 11):
                d.rectangle((x, y, x + 1, y + 1), fill="#305463")
    else:
        d.rectangle((5, 2, 10, 4), fill="#a8d9cd")
        d.rectangle((3, 5, 12, 11), fill="#a8d9cd")
        d.rectangle((2, 11, 13, 12), fill="#a8d9cd")
        d.rectangle((7, 14, 8, 15), fill="#a8d9cd")
    return image.resize((size, size), Image.NEAREST)


def shapes(
    notification=None,
    gesture="idle",
    deploying=False,
    music=None,
    idle_seconds=0,
    native_sprites=False,
    **character,
):
    video = (music or {}).get("video") or {}
    watching = reactions.active(music, notification, character.get("activity", "idle"), deploying)
    reaction = video.get("reaction") or {}
    idle_frame = idle_seconds % 48
    idle_action = (
        idle_seconds >= 35
        and 35 <= idle_frame < 43
        and not notification
        and not watching
        and not deploying
        and not (music and music.get("is_playing"))
        and character.get("activity", "idle") == "idle"
    )
    if idle_action and character.get("style", "okabe") in ("okabe", "kurisu"):
        character["mouth"] = max(0, math.sin(idle_frame * 8)) * 0.25
        character["pose"] = "phone"
    if character.get("style") == "sonic":
        character["arms"] = not (notification or gesture == "present" or idle_action)
    if (
        music
        and music.get("is_playing")
        and not notification
        and character.get("activity", "idle") == "idle"
        and music.get("meter_active")
        and time.monotonic() - music.get("pulse_at", 0) < 2
    ):
        character["emotion"] = music.get("expression", "neutral")
    if (
        character.get("style") == "kurisu"
        and music
        and music.get("is_playing")
        and not notification
        and character.get("activity", "idle") == "idle"
    ):
        character["show_emphasis"] = False
    if watching:
        character["emotion"] = reactions.EMOTIONS.get(reaction.get("reaction"), "neutral")
        if character.get("style") == "kurisu":
            character["show_emphasis"] = False
    original = pip_face.shapes(**character)
    if watching:
        original = reactions.move(original, reaction, character.get("phase", 0), video.get("state"))
        if reaction:
            original.extend(
                reactions.decorations(
                    reaction,
                    character.get("phase", 0),
                    video.get("state"),
                    native_sprites=native_sprites,
                )
            )
    listening = (
        bool(music and music.get("is_playing"))
        and not notification
        and character.get("activity", "idle") == "idle"
    )
    if listening:
        phase = character.get("phase", 0)
        age = max(0, time.monotonic() - music.get("pulse_at", 0))
        level = music.get("level", 0) * max(0, 1 - age / 0.4)
        metered = music.get("meter_active") and age < 2
        # Keep the shoulders planted: taper head movement to zero at the neck.
        strength = level if metered else 0.2
        nod = strength * 10
        sway = math.sin(phase * 3.2) * strength * 8
        neck = 270 if character.get("style") == "pip" else 220

        def point(x, y):
            weight = max(0, min(1, (neck - y) / 110))
            return (x + sway * weight, y + nod * weight)

        moved = [original[0]]
        for kind, coords, fill, width in original[1:]:
            if kind == "rectangle":
                x, y, xx, yy = coords
                coords = (x, y, xx, y, xx, yy, x, yy)
                kind = "polygon"
            points = [point(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]
            moved.append((kind, tuple(v for p in points for v in p), fill, width))
        original = moved
        for n, x in enumerate((72, 390)):
            y = 85 + math.sin(phase * 1.5 + n * 2) * 10
            original.extend(
                [
                    ("ellipse", (x, y + 17, x + 11, y + 25), "#a8d9cd", 1),
                    ("rectangle", (x + 8, y, x + 11, y + 21), "#a8d9cd", 1),
                    (
                        "polygon",
                        (x + 8, y, x + 24, y + 5, x + 24, y + 10, x + 8, y + 5),
                        "#a8d9cd",
                        1,
                    ),
                ]
            )
    if idle_action:
        style = character.get("style", "okabe")
        if style == "sonic":
            original.extend(
                [
                    ("rectangle", (192, 216, 207, 259), "#edc59c", 1),
                    ("rectangle", (180, 252, 211, 271), "#f5f4ed", 1),
                ]
            )
            wag = math.sin(idle_frame * 6) * 8
            original.extend(
                [
                    ("polygon", (280, 242, 309, 236, 326, 191, 311, 185, 289, 218), "#edc59c", 1),
                    ("ellipse", (306, 174, 338, 204), "#f5f4ed", 1),
                    ("line", (321, 183, 321 + wag, 151), "#f5f4ed", 12),
                    ("ellipse", (315 + wag, 145, 327 + wag, 157), "#f5f4ed", 1),
                ]
            )
    if deploying:
        phase = character.get("phase", 0)
        for i in range(4):
            original.append(
                (
                    "rectangle",
                    (14 + i * 9, 14, 20 + i * 9, 20),
                    "#e9a176" if int(phase * 4) % 4 == i else "#416065",
                    1,
                )
            )
    if not notification and gesture != "present":
        return original
    sonic = character.get("style") == "sonic"
    scale, offset_x, offset_y = (0.9, 24, -20) if sonic else (0.68, 77, 0)
    out = [original[0]]
    for kind, coords, fill, width in original[1:]:
        out.append(
            (
                kind,
                tuple(
                    v * scale + (offset_x if i % 2 == 0 else offset_y) for i, v in enumerate(coords)
                ),
                fill,
                max(1, width * scale),
            )
        )
    # Forearms lead into the card; hands visibly grip its upper edge.
    if character.get("style") == "sonic":
        # Arms start at Sonic's narrower shoulders, not the human sleeve anchors.
        out.extend(
            [
                (
                    "polygon",
                    (210, 171, 211, 185, 174, 202, 131, 210, 119, 198, 167, 189),
                    "#b77251",
                    1,
                ),
                (
                    "polygon",
                    (272, 171, 283, 171, 313, 189, 361, 198, 354, 210, 305, 202, 274, 185),
                    "#e7a579",
                    1,
                ),
                ("rectangle", (113, 194, 133, 207), "#f8f6e9", 1),
                ("rectangle", (346, 194, 366, 207), "#f8f6e9", 1),
            ]
        )
        return out
    sleeve = "#e6e2d8" if character.get("style") == "okabe" else "#a88b72"
    if character.get("style") == "pip":
        sleeve = "#accdc1"
    out.append(("polygon", (170, 177, 165, 197, 133, 208, 113, 208, 113, 194, 151, 177), sleeve, 1))
    out.append(("polygon", (310, 177, 315, 197, 346, 208, 366, 208, 366, 194, 329, 177), sleeve, 1))
    return out


def card(notification, font_path=None, style=None):
    image = Image.new("RGBA", (480, 320))
    if not notification:
        return image
    d = ImageDraw.Draw(image)
    d.rectangle((12, 207, 468, 314), fill="#172b34", outline="#7ca99d")
    image.alpha_composite(icon(notification.get("source"), 32), (27, 225))

    def font(size):
        try:
            return ImageFont.truetype(font_path or "DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()

    def measure(text, f):
        return f.getlength(text) if hasattr(f, "getlength") else d.textsize(text, font=f)[0]

    def fit(text, f, width):
        text = str(text).replace("\n", " ")
        if measure(text, f) <= width:
            return text
        while text and measure(text + "…", f) > width:
            text = text[:-1]
        return text + "…"

    small, title = font(13), font(18)
    d.text((73, 218), notification.get("source", "system").upper(), font=small, fill="#a8d9cd")
    d.text((73, 236), fit(notification.get("title", ""), title, 375), font=title, fill="#fff5e8")
    body = notification.get("body", "")
    d.text((27, 274), fit(body, font(15), 420), font=font(15), fill="#c7d5d8")
    for x in (113, 346):
        d.rectangle((x, 200, x + 20, 217), fill="#f8f6e9" if style == "sonic" else "#ecc3a3")
        d.line((x + 7, 208, x + 7, 214), fill="#939994" if style == "sonic" else "#aa7e69")
        d.line((x + 13, 208, x + 13, 214), fill="#939994" if style == "sonic" else "#aa7e69")
    return image


@lru_cache(maxsize=8)
def media_title_strip(title, font_path, viewport):
    # Cache glyph rendering; each animation frame only crops the prepared strip.
    try:
        font = ImageFont.truetype(font_path or "DejaVuSans.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    width = (
        font.getlength(title) if hasattr(font, "getlength") else draw.textsize(title, font=font)[0]
    )
    strip = Image.new("RGBA", (max(viewport, int(math.ceil(width)) + 1), 28))
    ImageDraw.Draw(strip).text((0, 3), title, font=font, fill="#d9eee5")
    return strip, max(0, width - viewport)


def marquee_offset(travel, elapsed):
    if travel <= 0:
        return 0
    # Fixed peak speed regardless of title length, with eased turns and end holds.
    hold = 1.5
    leg = max(1, math.pi * travel / (2 * 24))
    tick = max(0, elapsed) % (2 * leg + 2 * hold)
    if tick < hold:
        return 0
    if tick < hold + leg:
        return travel * (1 - math.cos(math.pi * (tick - hold) / leg)) / 2
    if tick < 2 * hold + leg:
        return travel
    return travel * (1 + math.cos(math.pi * (tick - 2 * hold - leg) / leg)) / 2


def progress_fraction(video, now=None):
    if not video or video.get("stream_type") == "LIVE":
        return None
    duration, position = video.get("duration"), video.get("position")
    if (
        not isinstance(duration, (int, float))
        or not isinstance(position, (int, float))
        or not math.isfinite(duration)
        or not math.isfinite(position)
        or duration <= 0
        or position < 0
    ):
        return None
    now = time.monotonic() if now is None else now
    if video.get("state") == "PLAYING":
        position += max(0, now - video.get("position_received_at", now)) * video.get(
            "playback_rate", 1
        )
    return min(1, position / duration)


def music_card(music, phase=0, font_path=None):
    image = Image.new("RGBA", (480, 320))
    if not music or not (music.get("is_playing") or music.get("video")):
        return image
    d = ImageDraw.Draw(image)
    d.rectangle((0, 273, 480, 320), fill="#172b34")
    video = music.get("video")
    title = (
        video.get("title", "")
        if video
        else "{} · {}".format(music.get("title", "Music"), music.get("artist", ""))
    )
    left, viewport = (60, 400)
    app = video.get("app", "") if video else "Spotify"
    image.alpha_composite(icon(media_source(app), 32), (16, 280))
    strip, travel = media_title_strip(title, font_path, viewport)
    offset = round(marquee_offset(travel, phase))
    image.alpha_composite(strip.crop((offset, 0, offset + viewport, 28)), (left, 282))
    fraction = progress_fraction(video)
    if fraction is not None:
        d.rectangle((20, 313, 460, 316), fill="#38444b")
        if fraction > 0:
            d.rectangle((20, 313, 20 + round(440 * fraction), 316), fill="#f04444")
    return image


def render(
    notification=None, gesture="idle", font_path=None, deploying=False, music=None, **character
):
    image = Image.new("RGB", (480, 320))
    d = ImageDraw.Draw(image)
    for kind, coords, fill, width in shapes(
        notification, gesture, deploying=deploying, music=music, **character
    ):
        if kind == "line":
            d.line(coords, fill=fill, width=max(1, round(width)))
        else:
            getattr(d, kind)(coords, fill=fill)
    overlay = (
        card(notification, font_path, character.get("style"))
        if notification
        else music_card(music, character.get("phase", 0), font_path)
    )
    image.paste(overlay, (0, 0), overlay)
    return image

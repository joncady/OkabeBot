"""Shared content prop slot and generated pixel-art atlas. Python 3.7."""

import json
import math
from functools import lru_cache
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent / "assets"
SLOT = (46, 188, 56, 56)

# The parser names semantic props; only this mapping knows the art vocabulary.
PROP_KEYS = {
    "controller": "gaming",
    "screen": "cinema",
    "star": "comedy",
    "spark": "comedy",
    "book": "learning",
    "heart": "romance",
    "search": "mystery",
    "planet": "science",
    "ghost": "horror",
    "note": "music",
    "leaf": "nature",
    "paw": "nature",
    "food": "food",
    "weight": "fitness",
    "compass": "travel",
    "wheel": "travel",
    "chat": "talk",
    "camera": "cinema",
    "tools": "diy",
    "chip": "technology",
    "moon": "relaxation",
    "shield": "cinema",
    "hat": "cinema",
}


def available():
    try:
        atlas()
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def key(reaction):
    _, manifest = atlas()
    if reaction.get("prop") == "ball":
        return manifest.get("sports", {}).get(reaction.get("sport"), "soccer")
    return manifest.get("mapping", PROP_KEYS).get(reaction.get("prop"), "cinema")


def position(phase, state):
    x, y, w, h = SLOT
    bob = round(math.sin(phase * 1.4) * 2) if state == "PLAYING" else 0
    return x, y + bob, w, h


@lru_cache(maxsize=1)
def atlas():
    manifest = json.loads((ROOT / "content-props.json").read_text())
    image_name = manifest["image"]
    if not isinstance(image_name, str) or Path(image_name).name != image_name:
        raise ValueError("Atlas image must be a local filename")
    order = manifest["order"]
    if not isinstance(order, list) or not order or len(set(order)) != len(order):
        raise ValueError("Invalid atlas order")
    if not all(isinstance(n, str) for n in order):
        raise ValueError("Invalid atlas keys")
    if any(type(manifest[k]) is not int or manifest[k] <= 0 for k in ("columns", "rows")):
        raise ValueError("Invalid atlas dimensions")
    if len(order) > manifest["columns"] * manifest["rows"]:
        raise ValueError("Atlas exceeds grid")
    mapped = list(manifest.get("mapping", {}).values()) + list(manifest.get("sports", {}).values())
    if any(n not in order for n in mapped) or "cinema" not in order or "soccer" not in order:
        raise ValueError("Unknown atlas mapping")
    with Image.open(str(ROOT / image_name)) as im:
        for name, box in manifest.get("rectangles", {}).items():
            if (
                name not in order
                or not isinstance(box, (list, tuple))
                or len(box) != 4
                or any(type(v) is not int for v in box)
                or not 0 <= box[0] < box[2] <= im.width
                or not 0 <= box[1] < box[3] <= im.height
            ):
                raise ValueError("Invalid atlas crop")
        return im.convert("RGBA"), manifest


@lru_cache(maxsize=24)
def sprite(name):
    sheet, manifest = atlas()
    index = manifest["order"].index(name)
    cols, rows = manifest["columns"], manifest["rows"]
    x, y = index % cols, index // cols
    box = manifest.get("rectangles", {}).get(name) or (
        round(x * sheet.width / cols),
        round(y * sheet.height / rows),
        round((x + 1) * sheet.width / cols),
        round((y + 1) * sheet.height / rows),
    )
    tile = sheet.crop(box)
    bounds = tile.getbbox()
    if bounds:
        tile = tile.crop(bounds)
    # Preserve real alpha and aspect ratio, snap to a 32px logical grid.
    tile.thumbnail((32, 32), Image.NEAREST)
    result = Image.new("RGBA", (32, 32))
    result.alpha_composite(tile, ((32 - tile.width) // 2, (32 - tile.height) // 2))
    return result


@lru_cache(maxsize=24)
def runs(name):
    image = sprite(name)
    result = []
    for y in range(32):
        x = 0
        while x < 32:
            color = image.getpixel((x, y))
            end = x + 1
            while end < 32 and image.getpixel((end, y)) == color:
                end += 1
            if color[3] > 127:
                result.append((x, y, end, "#%02x%02x%02x" % color[:3]))
            x = end
    return tuple(result)


def shapes(reaction, phase, state):
    x, y, w, h = position(phase, state)
    return [
        (
            "rectangle",
            (x + px * w / 32, y + py * h / 32, x + end * w / 32, y + (py + 1) * h / 32),
            color,
            1,
        )
        for px, py, end, color in runs(key(reaction))
    ]

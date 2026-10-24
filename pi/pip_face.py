"""Pip's vector face: shared Tk animation and Pillow preview, Python 3.7."""

import math
from PIL import Image, ImageDraw

EMOTIONS = ("neutral", "happy", "curious", "concerned", "excited")
ACTIVITIES = ("idle", "listening", "thinking", "speaking")


def pip_shapes(emotion="neutral", intensity=0.6, mouth=0, phase=0, activity="idle", palette=None):
    out = []

    def add(kind, coords, fill, width=1):
        out.append((kind, coords, fill, width))

    palette = palette or {}
    bg, shell, dark, light = (
        palette.get("background", "#101e25"),
        palette.get("shell", "#accdc1"),
        "#203b40",
        palette.get("accent", "#a5f4ce"),
    )
    add("rectangle", (0, 0, 480, 320), bg)
    bounce = math.sin(phase * (5 if emotion == "excited" else 1.7)) * (
        3 if emotion == "excited" else 1
    )

    def shifted(coords):
        return tuple(v + (bounce if i % 2 else 0) for i, v in enumerate(coords))

    def draw(kind, coords, color, width=1):
        add(kind, shifted(coords), color, width)

    add("ellipse", (133, 276, 347, 292), "#0a141c")
    draw("line", (240, 60, 240, 36), shell, 7)
    draw("ellipse", (231, 22, 249, 40), "#f3c177" if activity == "thinking" else light)
    draw("rectangle", (83, 128, 106, 195), "#5c9389")
    draw("rectangle", (374, 128, 397, 195), "#5c9389")
    draw(
        "polygon",
        (123, 60, 357, 60, 380, 83, 380, 246, 357, 269, 123, 269, 100, 246, 100, 83),
        shell,
    )
    draw(
        "polygon",
        (137, 81, 343, 81, 358, 96, 358, 231, 343, 246, 137, 246, 122, 231, 122, 96),
        dark,
    )
    blink = phase % 4.7 < 0.16
    for x in (184, 296):
        if blink:
            draw("line", (x - 21, 155, x + 21, 155), light, 6)
        elif emotion == "happy":
            draw("line", (x - 21, 158, x - 13, 147, x, 143, x + 13, 147, x + 21, 158), light, 7)
        else:
            h = 21 + (6 * intensity if emotion == "excited" else 0)
            gaze = 5 * math.sin(phase * 0.9) if activity == "thinking" else 0
            draw("ellipse", (x - 17 + gaze, 155 - h, x + 17 + gaze, 155 + h), light)
            draw("ellipse", (x - 7 + gaze, 141 - h, x + 1 + gaze, 149 - h), "#e3fff1")
    if emotion == "concerned":
        brows = [(160, 119, 205, 109), (275, 109, 320, 119)]
    elif emotion == "curious":
        brows = [(160, 112 - 12 * intensity, 205, 105 - 12 * intensity), (275, 120, 320, 120)]
    else:
        brows = [(160, 115, 205, 115), (275, 115, 320, 115)]
    for brow in brows:
        draw("line", brow, shell, 5)
    if mouth > 0.08:
        h = 5 + mouth * 25
        draw("ellipse", (216 - mouth * 7, 214 - h / 2, 264 + mouth * 7, 214 + h / 2), "#0a2028")
        draw("line", (225, 213 + h / 3, 255, 213 + h / 3), "#78bfab", 4)
    elif emotion == "concerned":
        draw("line", (222, 222, 234, 215, 246, 215, 258, 222), light, 4)
    else:
        depth = 9 if emotion in ("happy", "excited") else 4
        draw("line", (216, 209, 228, 216 + depth, 252, 216 + depth, 264, 209), light, 4)
    if emotion in ("happy", "excited"):
        draw("ellipse", (145, 187, 170, 194), "#d79588")
        draw("ellipse", (310, 187, 335, 194), "#d79588")
    for i in range(3):
        color = (
            light
            if activity == "listening" or (activity == "thinking" and int(phase * 3) % 3 == i)
            else "#466b64"
        )
        add("ellipse", (222 + i * 16, 299, 228 + i * 16, 305), color)
    return out


def shapes(style="okabe", **kwargs):
    if style == "pip":
        return pip_shapes(**kwargs)
    if __package__:
        from .okabe_face import shapes as okabe_shapes
    else:
        from okabe_face import shapes as okabe_shapes

    return okabe_shapes(**kwargs)


def render(**kwargs):
    image = Image.new("RGB", (480, 320))
    draw = ImageDraw.Draw(image)
    for kind, xy, color, width in shapes(**kwargs):
        if kind == "line":
            draw.line(xy, fill=color, width=width)
        else:
            getattr(draw, kind)(xy, fill=color)
    return image

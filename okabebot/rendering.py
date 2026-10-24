"""480x320 layouts rendered on the Mac."""

import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

SIZE = (480, 320)
THEMES = {
    "ocean": ("#101923", "#edf5fc", "#64dcc8"),
    "paper": ("#f3eddc", "#202a32", "#286b61"),
    "alert": ("#271a18", "#fff3e7", "#ffad70"),
}


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(Path(__file__).parent / "assets" / name), size)


def wrap(text, f, width):
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=f) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            for char in word:
                if draw.textlength(line + char, font=f) > width:
                    lines.append(line)
                    line = ""
                line += char
        lines.append(line)
    return lines


def message(text, title="", theme="ocean"):
    if theme not in THEMES:
        raise ValueError("Unknown theme")
    if not text.strip() or len(text) > 2000 or len(title) > 60:
        raise ValueError("Use 1–2000 text characters and a title of at most 60 characters")
    bg, fg, accent = THEMES[theme]
    img = Image.new("RGB", SIZE, bg)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((20, 20, 24, 43), radius=2, fill=accent)
    tf = font(16, True)
    if d.textlength(title.upper(), font=tf) > 406:
        raise ValueError("Title is too wide; shorten it")
    d.text((36, 21), title.upper() or "HARDWARE LAB", font=tf, fill=accent)
    for size in (34, 30, 26, 22, 18):
        f = font(size)
        lines = wrap(text, f, 432)
        line_height = size + 8
        if len(lines) * line_height <= 216:
            break
    else:
        raise ValueError("Message will not fit legibly; shorten it or use multiple messages")
    y = 70 + max(0, (216 - len(lines) * line_height) // 2)
    for line in lines:
        d.text((24, y), line, font=f, fill=fg)
        y += line_height
    d.line((24, 300, 456, 300), fill=accent, width=1)
    return img


def load_image(path, fit="contain"):
    if fit not in ("contain", "cover"):
        raise ValueError("fit must be contain or cover")
    p = Path(path).expanduser()
    if p.stat().st_size > 10_000_000:
        raise ValueError("Image must be smaller than 10 MB")
    with Image.open(p) as original:
        if original.width * original.height > 20_000_000:
            raise ValueError("Image must be under 20 megapixels")
        img = ImageOps.exif_transpose(original).convert("RGBA")
        background = Image.new("RGBA", img.size, "#101923")
        background.alpha_composite(img)
        img = background.convert("RGB")
    if fit == "cover":
        return ImageOps.fit(img, SIZE, method=Image.Resampling.LANCZOS)
    img.thumbnail(SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", SIZE, "#101923")
    canvas.paste(img, ((480 - img.width) // 2, (320 - img.height) // 2))
    return canvas


def png(img):
    data = io.BytesIO()
    img.save(data, "PNG")
    return data.getvalue()

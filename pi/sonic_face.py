"""Front-facing pixel Sonic with separate resting arms for alternate poses."""


def shapes(
    emotion="neutral",
    intensity=0.6,
    mouth=0,
    phase=0,
    activity="idle",
    palette=None,
    arms=True,
    motion=None,
):
    motion = motion or {}
    out = [("rectangle", (0, 0, 480, 320), (palette or {}).get("background", "#101e25"), 1)]

    def rect(x, y, xx, yy, color):
        lift = -round(motion.get("foot", 0)) if y >= 71 and x >= 63 else 0
        out.append(("rectangle", (x * 4, y * 4 + lift, xx * 4 - 1, yy * 4 - 1 + lift), color, 1))

    def poly(points, color):
        out.append(("polygon", tuple(v * 4 for v in points), color, 1))

    blue, light, skin, white = "#1765d1", "#428cf2", "#edc59c", "#f5f4ed"
    poly(
        (
            43,
            22,
            29,
            18,
            37,
            31,
            25,
            34,
            38,
            41,
            29,
            49,
            46,
            48,
            47,
            56,
            77,
            49,
            88,
            35,
            77,
            17,
            57,
            12,
        ),
        blue,
    )
    poly((44, 23, 45, 7, 56, 18), blue)
    poly((67, 18, 78, 8, 79, 29), blue)
    poly((47, 20, 48, 12, 53, 19), skin)
    poly((70, 19, 76, 13, 76, 24), skin)
    rect(47, 19, 75, 44, blue)
    rect(48, 21, 52, 29, light)
    rect(47, 30, 62, 42, white)
    rect(61, 27, 75, 42, white)
    gaze = -1 if activity == "thinking" else round(motion.get("gaze", 0))
    if not motion.get("blink", phase % 4.7 < 0.16):
        rect(56 + gaze, 32, 59 + gaze, 41, "#25883d")
        rect(68 + gaze, 30, 71 + gaze, 41, "#25883d")
        rect(58 + gaze, 33, 60 + gaze, 41, "#101a28")
        rect(70 + gaze, 31, 72 + gaze, 41, "#101a28")
    else:
        rect(49, 36, 60, 37, "#101a28")
        rect(64, 35, 73, 36, "#101a28")
    poly((45, 40, 74, 39, 80, 43, 74, 50, 53, 51, 44, 46), skin)
    rect(73, 39, 81, 42, "#101a28")
    rect(62, 46, 72, 47 if mouth < 0.08 else 49, "#653d38")
    if emotion in ("happy", "excited"):
        rect(70, 45, 73, 46, "#653d38")
    rect(51, 51, 70, 65, blue)
    rect(56, 52, 65, 62, skin)
    if arms:
        rect(48, 54, 52, 65, skin)
        rect(70, 53, 74, 63, skin)
        rect(45, 63, 53, 68, white)
        rect(70, 62, 78, 67, white)
    rect(54, 64, 58, 72, blue)
    rect(65, 64, 69, 72, blue)
    rect(47, 71, 59, 76, "#d93836")
    rect(64, 71, 78, 76, "#d93836")
    rect(51, 71, 54, 75, white)
    rect(68, 71, 71, 75, white)
    rect(46, 76, 60, 78, white)
    rect(63, 76, 79, 78, white)
    return out

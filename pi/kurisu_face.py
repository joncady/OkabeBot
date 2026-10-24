"""Original rectangle-based pixel interpretation of Makise Kurisu."""

import math


def shapes(emotion="neutral", intensity=0.6, mouth=0, phase=0, activity="idle", palette=None):
    palette = palette or {}
    out = [("rectangle", (0, 0, 480, 320), palette.get("background", "#101e25"), 1)]
    bob = round(math.sin(phase * (5 if emotion == "excited" else 1.7)))

    def rect(x, y, xx, yy, color):
        out.append(("rectangle", (x * 4, (y + bob) * 4, xx * 4 - 1, (yy + bob) * 4 - 1), color, 1))

    hair, light, skin, shade = "#843e37", "#b75d46", "#f0cdb9", "#d2a38e"
    # Long auburn hair, white shirt, red tie, and a loose tan jacket.
    rect(39, 13, 81, 68, hair)
    rect(35, 31, 43, 70, hair)
    rect(77, 29, 86, 71, hair)
    rect(40, 35, 44, 65, light)
    rect(78, 34, 81, 67, light)
    rect(35, 60, 85, 74, "#947461")
    rect(32, 65, 43, 74, "#b5997a")
    rect(77, 65, 88, 74, "#b5997a")
    rect(46, 54, 74, 74, "#f4eee4")
    rect(54, 47, 66, 56, shade)
    rect(56, 48, 64, 55, skin)
    rect(58, 57, 62, 62, "#a23645")
    rect(57, 62, 63, 73, "#7e293c")
    rect(47, 54, 54, 58, "#d2d2cf")
    rect(66, 54, 73, 58, "#d2d2cf")
    rect(44, 19, 76, 44, skin)
    rect(47, 42, 73, 48, skin)
    rect(52, 47, 68, 51, skin)
    rect(42, 12, 78, 24, hair)
    rect(47, 8, 72, 16, hair)
    rect(46, 13, 65, 16, light)
    for x, y in [(44, 20), (48, 23), (52, 26), (70, 23), (74, 20)]:
        rect(x, y, x + 4, y + 8, hair)
    rect(61, 17, 65, 23, light)
    if emotion == "excited":
        rect(83, 14, 85, 21, "#f2ca70")
        rect(83, 23, 85, 25, "#f2ca70")
    blink = phase % 4.7 < 0.16
    for x in (48, 65):
        rect(x, 32, x + 8, 33, "#49303a")
        if not blink:
            rect(x, 33, x + 8, 37, "#fff3e7")
            rect(x + 3, 33, x + 6, 37, "#526a94")
            rect(x + 4, 33, x + 5, 36, "#29364e")
    rect(48, 28 if emotion != "curious" else 26, 56, 29 if emotion != "curious" else 27, hair)
    rect(65, 27 if emotion == "concerned" else 28, 73, 28 if emotion == "concerned" else 29, hair)
    if emotion == "curious":
        rect(65, 30, 73, 31, hair)
    rect(60, 37, 62, 40, shade)
    if emotion in ("happy", "excited"):
        rect(47, 39, 52, 41, "#e6a39e")
        rect(69, 39, 74, 41, "#e6a39e")
    if mouth > 0.08:
        rect(56, 43, 65, 45 + round(mouth * (3 + intensity)), "#703e45")
        rect(57, 43, 64, 44, "#fff0df")
    else:
        rect(56, 44, 65, 45, "#985962")
        if emotion in ("happy", "excited"):
            rect(65, 43, 67, 44, "#985962")
    for i in range(3):
        color = (
            palette.get("accent", "#a5f4ce")
            if activity == "listening" or (activity == "thinking" and int(phase * 3) % 3 == i)
            else "#466b64"
        )
        rect(55 + i * 5, 77, 57 + i * 5, 79, color)
    return out

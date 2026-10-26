"""Original pixel-art interpretation of Rintaro Okabe; rectangle-only animation."""

import math


def shapes(
    emotion="neutral", intensity=0.6, mouth=0, phase=0, activity="idle", palette=None, pose="rest"
):
    palette = palette or {}
    bg = palette.get("background", "#101e25")
    out = [("rectangle", (0, 0, 480, 320), bg, 1)]
    # Work on a 120x80 pixel grid, then scale exactly 4x for the LCD.
    bob = round(math.sin(phase * (5 if emotion == "excited" else 1.7)))

    def rect(x1, y1, x2, y2, color):
        out.append(
            ("rectangle", (x1 * 4, (y1 + bob) * 4, x2 * 4 - 1, (y2 + bob) * 4 - 1), color, 1)
        )

    skin, shade, hair, shine = "#e0bba0", "#bc927b", "#242426", "#3b3836"
    coat, seam, shirt = "#e9e5dc", "#a8aaa7", "#57514d"
    rect(34, 72, 87, 75, "#091319")
    # Lab coat, dark shirt and angular lapels.
    phone = pose == "phone"
    rect(35, 57, 80 if phone else 85, 72, seam)
    rect(31, 62, 40, 73, coat)
    if not phone:
        rect(80, 62, 89, 73, coat)
    rect(38, 57, 80 if phone else 82, 73, coat)
    rect(51, 54, 69, 73, shirt)
    rect(53, 48, 67, 58, shade)
    rect(55, 49, 65, 57, skin)
    for row in range(8):
        rect(44 + row, 54 + row, 49 + row, 55 + row, seam)
        rect(71 - row, 54 + row, 76 - row, 55 + row, seam)
    rect(73, 64, 81, 65, seam)
    rect(76, 61, 77, 65, "#505756")
    # Ears, narrow jaw and swept-back, uneven hair silhouette.
    rect(41, 27, 79, 40, shade)
    rect(45, 16, 75, 44, skin)
    rect(48, 43, 72, 49, skin)
    rect(52, 49, 68, 51, shade)
    rect(42, 17, 46, 32, hair)
    rect(74, 17, 78, 33, hair)
    rect(42, 12, 77, 21, hair)
    rect(47, 8, 74, 16, hair)
    rect(52, 5, 68, 12, hair)
    rect(68, 9, 79, 15, hair)
    rect(77, 13, 82, 20, hair)
    rect(38, 16, 45, 21, hair)
    rect(44, 20, 50, 25, hair)
    rect(49, 17, 54, 21, hair)
    rect(48, 11, 53, 13, shine)
    rect(54, 8, 64, 10, shine)
    rect(65, 12, 73, 14, shine)
    # Small angular eyes and brows; happy narrows the eyes, curious raises one brow.
    blink = phase % 4.7 < 0.16
    for x in (48, 65):
        ey = 32
        rect(x, ey, x + 8, ey + (1 if blink or emotion == "happy" else 3), "#f3e8da")
        gaze = 1 if activity == "thinking" and math.sin(phase) > 0 else 0
        rect(x + 4 + gaze, ey, x + 6 + gaze, ey + (1 if blink else 3), hair)
    left_y = 26 if emotion == "curious" else 28
    right_y = 27 if emotion == "concerned" else 28
    rect(47, left_y, 57, left_y + 2, hair)
    rect(64, right_y, 74, right_y + 2, hair)
    if emotion in ("concerned", "excited"):
        rect(54, 29, 57, 31, hair)
        rect(64, 29, 67, 31, hair)
    rect(60, 34, 62, 39, shade)
    rect(58, 39, 63, 40, shade)
    # Mouth follows the same audio envelope used by the original Pip renderer.
    if mouth > 0.08:
        height = 2 + round(mouth * (4 + intensity))
        rect(55, 43, 66, 43 + height, "#523b37")
        rect(56, 43, 65, 44, "#f4e7d4")
    else:
        rect(55, 44, 65, 45, "#74594e")
        if emotion in ("happy", "excited"):
            rect(65, 43, 68, 44, "#74594e")
    # Recognizable faint chin stubble.
    for x in (55, 59, 63):
        rect(x, 48, x + 1, 49, "#8e7468")
    if phone:
        # Replace the resting right sleeve; every part follows the body's pixel-grid bob.
        rect(76, 58, 82, 64, coat)
        rect(80, 61, 87, 66, coat)
        rect(83, 44, 88, 64, coat)
        rect(82, 44, 88, 48, seam)
        rect(81, 38, 87, 45, skin)
        rect(78, 32, 84, 45, "#131a24")
        rect(79, 34, 83, 42, "#52728a")
    return out

"""Original pixel-art interpretation of Rintaro Okabe; rectangle-only animation."""

import math


def shapes(
    emotion="neutral",
    intensity=0.6,
    mouth=0,
    phase=0,
    activity="idle",
    palette=None,
    pose="rest",
    motion=None,
):
    palette = palette or {}
    bg = palette.get("background", "#101e25")
    out = [("rectangle", (0, 0, 480, 320), bg, 1)]
    # Work on a 120x80 pixel grid, then scale exactly 4x for the LCD.
    motion = motion or {}
    bob = 0 if motion else round(math.sin(phase * (5 if emotion == "excited" else 1.7)))

    head = False

    def rect(x1, y1, x2, y2, color):
        dx = round(motion.get("head_x", 0)) if head else 0
        dy = round(motion.get("head_y", 0)) if head else 0
        out.append(
            (
                "rectangle",
                (x1 * 4 + dx, (y1 + bob) * 4 + dy, x2 * 4 - 1 + dx, (y2 + bob) * 4 - 1 + dy),
                color,
                1,
            )
        )

    skin, shade, hair, shine = "#e0bba0", "#bc927b", "#242426", "#3b3836"
    coat, seam, shirt = "#e9e5dc", "#a8aaa7", "#57514d"
    rect(34, 72, 87, 75, "#091319")
    # Lab coat, dark shirt and angular lapels.
    phone = pose in ("phone", "wave", "read", "write", "review", "stretch")
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
    head = True
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
    blink = motion.get("blink", phase % 4.7 < 0.16)
    for x in (48, 65):
        ey = 32
        rect(x, ey, x + 8, ey + (1 if blink or emotion == "happy" else 3), "#f3e8da")
        gaze = 1 if activity == "thinking" and math.sin(phase) > 0 else round(motion.get("gaze", 0))
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
    head = False
    if phone:
        weight = motion.get("pose_weight", 1)
        shift = (
            0
            if pose == "wave"
            else 20 - round(weight * (10 if pose in ("read", "write", "review") else 20))
        )
        # Replace the resting right sleeve; every part follows the body's pixel-grid bob.
        rect(76, 58, 82, 64, coat)
        rect(80, 61, 87, 66, coat)
        rect(83, 44 + shift, 88, max(65, 45 + shift), coat)
        rect(82, 44 + shift, 88, 48 + shift, seam)
        rect(81, 38 + shift, 87, 45 + shift, skin)
        if pose == "wave":
            wag = round(math.sin(phase * 8) * 2)
            rect(81 + wag, 30, 88 + wag, 42, skin)
            for finger in range(3):
                rect(81 + wag + finger * 2, 27 - finger % 2, 82 + wag + finger * 2, 33, skin)
        elif pose in ("read", "write", "review"):
            rect(78, 34 + shift, 89, 47 + shift, "#546b69")
            rect(79, 35 + shift, 88, 46 + shift, "#eee2bd")
            if pose == "read":
                rect(83, 35 + shift, 84, 46 + shift, "#a68a69")
            else:
                for row in (37, 40, 43):
                    rect(80, row + shift, 87, row + 1 + shift, "#a68a69")
                rect(
                    85 + round(motion.get("hand", 0)),
                    36 + shift,
                    86 + round(motion.get("hand", 0)),
                    43 + shift,
                    "#d4a75d",
                )
        elif pose == "stretch":
            lift = max(0, round(-motion.get("body_y", 0)))
            rect(82, 30 - lift, 88, 43, skin)
            rect(83, 28 - lift, 87, 32, skin)
        else:
            rect(78, 32 + shift, 84, 45 + shift, "#131a24")
            rect(79, 34 + shift, 83, 42 + shift, "#52728a")
    return out

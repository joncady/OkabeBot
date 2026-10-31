"""Original rectangle-based pixel interpretation of Makise Kurisu."""

import math


def shapes(
    emotion="neutral",
    intensity=0.6,
    mouth=0,
    phase=0,
    activity="idle",
    palette=None,
    show_emphasis=True,
    pose="rest",
    motion=None,
    arms=True,
):
    palette = palette or {}
    out = [("rectangle", (0, 0, 480, 320), palette.get("background", "#101e25"), 1)]
    motion = motion or {}
    bob = 0 if motion else round(math.sin(phase * (5 if emotion == "excited" else 1.7)))

    head = True

    def rect(x, y, xx, yy, color):
        dx = round(motion.get("head_x", 0)) if head else 0
        dy = round(motion.get("head_y", 0)) if head else 0
        out.append(
            (
                "rectangle",
                (x * 4 + dx, (y + bob) * 4 + dy, xx * 4 - 1 + dx, (yy + bob) * 4 - 1 + dy),
                color,
                1,
            )
        )

    hair, light, skin, shade = "#843e37", "#b75d46", "#f0cdb9", "#d2a38e"
    # Long auburn hair, white shirt, red tie, and a loose tan jacket.
    rect(39, 13, 81, 68, hair)
    rect(35, 31, 43, 70, hair)
    rect(77, 29, 86, 71, hair)
    rect(40, 35, 44, 65, light)
    rect(78, 34, 81, 67, light)
    head = False
    working = pose in ("read", "write", "review", "computer")
    phone = pose in ("phone", "wave", "stretch")
    rect(35, 60, 77 if phone else 85, 74, "#947461")
    if not working and arms:
        rect(32, 65, 43, 74, "#b5997a")
    if not phone and not working and arms:
        rect(77, 65, 88, 74, "#b5997a")
    rect(46, 54, 74, 74, "#f4eee4")
    rect(54, 47, 66, 56, shade)
    rect(56, 48, 64, 55, skin)
    rect(58, 57, 62, 62, "#a23645")
    rect(57, 62, 63, 73, "#7e293c")
    rect(47, 54, 54, 58, "#d2d2cf")
    rect(66, 54, 73, 58, "#d2d2cf")
    head = True
    rect(44, 19, 76, 44, skin)
    rect(47, 42, 73, 48, skin)
    rect(52, 47, 68, 51, skin)
    rect(42, 12, 78, 24, hair)
    rect(47, 8, 72, 16, hair)
    rect(46, 13, 65, 16, light)
    for x, y in [(44, 20), (48, 23), (52, 26), (70, 23), (74, 20)]:
        rect(x, y, x + 4, y + 8, hair)
    rect(61, 17, 65, 23, light)
    if emotion == "excited" and show_emphasis:
        rect(83, 14, 85, 21, "#f2ca70")
        rect(83, 23, 85, 25, "#f2ca70")
    blink = motion.get("blink", phase % 4.7 < 0.16)
    gaze = (
        (1 if math.sin(phase * 0.8) > 0 else -1)
        if activity == "thinking"
        else round(motion.get("gaze", 0))
    )
    for x in (48, 65):
        rect(x, 32, x + 8, 33, "#49303a")
        if not blink:
            rect(x, 33, x + 8, 37, "#fff3e7")
            gy = max(0, min(1, round(motion.get("gaze_y", 0))))
            rect(x + 3 + gaze, 33 + gy, x + 6 + gaze, 37, "#526a94")
            rect(x + 4 + gaze, 33 + gy, x + 5 + gaze, 36 + gy, "#29364e")
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
    head = False
    if working:
        from ..workbench import draw

        draw(out, pose, motion, phase, "#b5997a", skin, "#947461")
        return out
    if phone:
        weight = motion.get("pose_weight", 1)
        shift = (
            0
            if pose == "wave"
            else 20 - round(weight * (10 if pose in ("read", "write", "review") else 20))
        )
        # The raised arm replaces its resting sleeve and shares the face/body transform.
        rect(76, 58, 82, 64, "#b5997a")
        rect(80, 61, 87, 66, "#b5997a")
        rect(83, 44 + shift, 88, max(65, 45 + shift), "#b5997a")
        rect(82, 44 + shift, 88, 48 + shift, "#947461")
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

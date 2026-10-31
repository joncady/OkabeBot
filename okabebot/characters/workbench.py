"""Anchored pixel work poses for characters that implement a human workbench rig."""

import math


def draw(out, pose, motion, phase, sleeve, skin, cuff):
    """Paper stays on a perspective desk; shoulders, elbows, wrists stay connected."""
    weight = motion.get("pose_weight", 1)
    drop = round((1 - weight) * 13)
    stroke = round(motion.get("hand", 0))
    computer = pose == "computer"

    def rect(x1, y1, x2, y2, color):
        out.append(("rectangle", (x1 * 4, y1 * 4, x2 * 4 - 1, y2 * 4 - 1), color, 1))

    def polygon(points, color):
        out.append(("polygon", tuple(v * 4 for point in points for v in point), color, 1))

    def segment(start, end, half_width, color):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = max(1, math.hypot(dx, dy))
        nx, ny = -dy / length * half_width, dx / length * half_width
        polygon(
            [
                (round(start[0] + nx), round(start[1] + ny)),
                (round(start[0] - nx), round(start[1] - ny)),
                (round(end[0] - nx), round(end[1] - ny)),
                (round(end[0] + nx), round(end[1] + ny)),
            ],
            color,
        )

    # Desk top and front edge. Props inherit its coordinate frame.
    polygon([(23, 66 + drop), (91, 66 + drop), (103, 76 + drop), (13, 76 + drop)], "#8a6854")
    rect(13, 76 + drop, 103, 79 + drop, "#4e4141")
    if computer:
        polygon([(44, 68 + drop), (73, 68 + drop), (79, 73 + drop), (41, 73 + drop)], "#c5c6b6")
        for row in range(2):
            for key in range(7):
                rect(
                    46 + key * 4, 69 + drop + row * 2, 48 + key * 4, 70 + drop + row * 2, "#53656a"
                )
    else:
        polygon([(47, 67 + drop), (72, 67 + drop), (77, 74 + drop), (44, 74 + drop)], "#4f5350")
        polygon([(48, 67 + drop), (71, 67 + drop), (75, 73 + drop), (45, 73 + drop)], "#eee4c5")
        rect(51, 68 + drop, 66, 69 + drop, "#a59678")
        rect(50, 70 + drop, 62, 71 + drop, "#a59678")
        rect(49, 72 + drop, 55 + stroke, 73 + drop, "#7e7565")
    # Interpolate hand position from rest; shoulders never move to meet the prop.
    hands = []
    for side in (-1, 1):
        shoulder = (35, 60) if side < 0 else (84, 60)
        rest = (35, 72) if side < 0 else (84, 72)
        target = (52, 70) if side < 0 else (66 + stroke, 70)
        if computer:
            target = (53, 69 + stroke) if side < 0 else (65, 70 - stroke)
        wrist = tuple(round(a + (b - a) * weight) for a, b in zip(rest, target))
        elbow = (round(shoulder[0] + side * 2 * (1 - weight) - side * 5 * weight), 67)
        ex, ey = elbow
        wx, wy = wrist
        rect(shoulder[0] - 4, shoulder[1] - 2, shoulder[0] + 4, shoulder[1] + 4, sleeve)
        segment(shoulder, elbow, 3.5, sleeve)
        segment(elbow, wrist, 2.5, sleeve)
        # A filled overlapping joint prevents the bend from revealing a desk-colored gap.
        rect(ex - 3, ey - 3, ex + 4, ey + 4, sleeve)
        rect(wx - 3, wy - 2, wx + 3, wy + 1, cuff)
        rect(wx - 2, wy - 2, wx + 3, wy + 1, skin)
        hands.append(wrist)
    if pose == "write":
        # Fingers grip the pencil; the nib stays on the sheet as the hand strokes.
        wx, wy = hands[1]
        out.append(("line", ((wx + 3) * 4, (wy - 6) * 4, (wx - 1) * 4, (wy + 2) * 4), "#d8a657", 5))
        rect(wx, wy - 2, wx + 3, wy, skin)
        rect(wx - 1, wy + 1, wx, wy + 2, "#3a4247")
    elif pose == "review":
        # A small check mark lies on the page, rather than floating by the head.
        out.append(
            (
                "line",
                (59 * 4, (70 + drop) * 4, 61 * 4, (72 + drop) * 4, 66 * 4, (68 + drop) * 4),
                "#557967",
                3,
            )
        )

    if computer:
        # Foreground back of the monitor intentionally occludes the lower face/torso.
        rect(57, 64 + drop, 64, 69 + drop, "#a7aca3")
        rect(48, 69 + drop, 73, 71 + drop, "#53656a")
        rect(40, 43 + drop, 81, 65 + drop, "#1d303d")
        rect(41, 44 + drop, 79, 63 + drop, "#344f59")
        rect(42, 44 + drop, 79, 45 + drop, "#819996")
        rect(58, 51 + drop, 62, 55 + drop, "#78988f")
        for x in range(48, 73, 4):
            rect(x, 60 + drop, x + 2, 61 + drop, "#1d303d")

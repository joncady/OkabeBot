"""Pure low-cost motion sampling; Python 3.7, no network or device actions."""

import math
from functools import lru_cache


@lru_cache(maxsize=1)
def catalog():
    try:
        from okabebot.characters import motion_catalog
    except ImportError:
        from characters import motion_catalog
    return motion_catalog()


def track(points, at):
    for (start, a), (end, b) in zip(points, points[1:]):
        if at <= end:
            t = min(1, max(0, (at - start) / (end - start)))
            t = t * t * (3 - 2 * t)  # Anticipation/settling without snapping.
            return a + (b - a) * t
    return points[-1][1] if points else 0


def sample(
    data, style, elapsed, activity="idle", blocked=False, stage="", reduced=False, face_seconds=None
):
    result = dict(
        clip="rest",
        pose="rest",
        body_y=0,
        head_x=0,
        head_y=0,
        gaze=0,
        gaze_y=0,
        hand=0,
        foot=0,
        pose_weight=0,
    )
    face_seconds = elapsed if face_seconds is None else face_seconds
    blink_at = (face_seconds + len(style) * 0.37) % 7.3
    result["blink"] = blink_at < 0.14 or (
        int(face_seconds // 7.3) % 3 == 1 and 0.32 < blink_at < 0.44
    )
    if reduced or blocked or activity != "idle" or not data:
        return result
    elapsed = max(0, elapsed)
    result["body_y"] = math.sin(elapsed * 1.15) * 0.6
    owned = data.get("definitions", {}).get(style, {})
    clips = owned.get("clips", data["clips"])
    clip = owned.get("work_stages", data.get("work_stages", {})).get(stage)
    if clip:
        at = elapsed % clips[clip]["duration"]
    else:
        playlist = data.get("characters", {}).get(style, [])
        if not playlist:
            return result
        cycle = data["idle_cycle_seconds"]
        slot = int(elapsed // cycle)
        # Character-specific spacing, bounded variation, no common synchronized loop.
        offset = data["idle_start_seconds"] + ((slot * 7 + len(style)) % 5)
        at = elapsed % cycle - offset
        clip = playlist[slot % len(playlist)]
        if at < 0 or at >= clips[clip]["duration"]:
            return result
    definition = clips[clip]
    fade = min(1, elapsed / 0.5) if stage else min(1, at / 0.5, (definition["duration"] - at) / 0.5)
    result["pose_weight"] = max(0, fade) ** 2 * (3 - 2 * max(0, fade))
    result.update(clip=clip, pose=definition["pose"])
    for channel, points in definition["tracks"].items():
        result[channel] += track(points, at)
    return result

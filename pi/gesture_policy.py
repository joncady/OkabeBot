"""Pure renderer-side eligibility for silent visual gestures."""


def wave_allowed(character, phase, notification, music, deploying, allow_media=False):
    return bool(
        character
        and character.get("activity") == "idle"
        and phase == "home"
        and not notification
        and not deploying
        and (allow_media is True or not (music.get("is_playing") or music.get("video")))
    )

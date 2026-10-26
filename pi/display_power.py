"""Apply kiosk power settings only after Tk has opened its X11 display. Python 3.7."""

import subprocess


def keep_awake(display, enabled=True):
    if not enabled:
        return True
    success = True
    for arguments in (("dpms", "force", "on"), ("-dpms",), ("s", "off"), ("s", "noblank")):
        try:
            result = subprocess.run(
                ["xset", "-display", display] + list(arguments),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            success = result.returncode == 0 and success
        except (OSError, subprocess.SubprocessError):
            success = False
    return success

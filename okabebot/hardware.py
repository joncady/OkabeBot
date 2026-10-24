"""Display/camera/Bluetooth endpoint with explicit uncertain-outcome errors."""

import subprocess
from .transport import device


def rpc(data):
    try:
        return device("display").rpc(data)
    except (OSError, RuntimeError, ValueError, TimeoutError, subprocess.SubprocessError) as exc:
        return {
            "outcome": "unknown",
            "error": str(exc),
            "detail": "Do not retry a press with a different request_id.",
        }

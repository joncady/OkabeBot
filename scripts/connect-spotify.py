#!/usr/bin/env python3
"""Authorize optional Spotify control even when Cast supplies metadata."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from okabebot.config import get_config, state_dir
from okabebot.spotify import Spotify

source = Spotify(state_dir(), get_config()["spotify"])
try:
    print("Open on this computer:", source.begin(), flush=True)
    while True:
        with source.lock:
            pending = source.pending
            if not pending or time.time() >= pending["expires"]:
                break
        time.sleep(1)
    granted = "user-modify-playback-state" in source.tokens.get("scope", "").split()
    print(
        "Playback control authorized." if granted else "Playback control authorization incomplete."
    )
finally:
    source.close()

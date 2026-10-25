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
    while source.pending and time.time() < source.pending["expires"]:
        time.sleep(1)
    print("Authorization finished." if source.tokens else "Authorization incomplete.")
finally:
    source.close()

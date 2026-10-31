#!/usr/bin/env python3
"""Silent local TTS timing probe; no microphone, speaker, tools or history writes."""

import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--text",
        default=(
            "The little observatory is ready for another experiment. "
            "A paper rocket waits beside the window. "
            "We can finish the checklist after a short break."
        ),
    )
    args = parser.parse_args()
    os.environ["OKABEBOT_CONFIG"] = str(args.config.expanduser().resolve())
    from okabebot import speech
    from okabebot.audio_buffer import buffered_chunks

    if speech.engine() != "local":
        parser.error(
            "This silent probe requires the local voice backend; cloud billing is excluded"
        )
    if not 1 <= len(args.text.strip()) <= 600:
        parser.error("Use 1–600 characters")
    first, count, size = None, 0, 0
    metrics = {}
    with speech.synthesis_session():
        start = time.monotonic()
        source = speech.pcm_chunks(args.text, "neutral", "calm")
        stream = buffered_chunks(source, metrics=metrics, first_chunk_bytes=9600)
        try:
            for chunk in stream:
                if first is None:
                    first = time.monotonic() - start
                count += 1
                size += len(chunk)
        finally:
            stream.close()
        elapsed = time.monotonic() - start
    print(
        json.dumps(
            {
                "probe": "silent_local_synthesis",
                "first_pcm_s": round(first, 3) if first is not None else None,
                "complete_pcm_s": round(elapsed, 3),
                "audio_s": round(size / 48000, 3),
                "packets": count,
                "full_buffer_wait_avoided_s": round(elapsed - first, 3) if first else None,
                "source_max_gap_s": metrics.get("source_max_gap_s"),
                "includes_network_or_playback": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

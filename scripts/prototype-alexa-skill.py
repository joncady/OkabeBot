#!/usr/bin/env python3
"""Exercise Alexa JSON -> real read-only tool -> reply, optionally Qwen -> MP3.

No server, cloud resources, uploads, speaker playback or physical actions.
"""

import argparse
import json
from pathlib import Path
import subprocess
import shutil
import time
import wave

from okabebot.alexa_skill import DEMO_TEXT, Prototype, fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice-output", type=Path, help="Generate generic demo MP3 locally")
    args = parser.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if args.voice_output and not ffmpeg:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            parser.error("Install ffmpeg or the alexa-prototype extra before generating audio")
    from okabebot import server

    skill = Prototype(
        "local-prototype",
        "local-test-user",
        {
            "get_device_health": server.get_device_health,
            "get_companion_locations": server.get_companion_locations,
        },
    )
    report = {}
    for name in ("LabStatusIntent", "LabLocationsIntent", "VoiceDemoIntent"):
        start = time.monotonic()
        reply = skill.handle(fixture(name))
        report[name] = {
            "seconds": round(time.monotonic() - start, 3),
            "speech_type": reply["response"]["outputSpeech"]["type"],
        }
    if args.voice_output:
        from okabebot import speech
        from okabebot.profiles import current_character
        import tempfile

        start = time.monotonic()
        first = None
        args.voice_output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as folder:
            wav_path = Path(folder) / "demo.wav"
            with wave.open(str(wav_path), "wb") as wav:
                wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                for chunk in speech.local_pcm_chunks(
                    DEMO_TEXT, "neutral", current_character()["default_voice"]
                ):
                    if first is None:
                        first = time.monotonic() - start
                    wav.writeframes(chunk)
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(wav_path),
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "48k",
                    str(args.voice_output),
                ],
                check=True,
                timeout=20,
            )
        report["generic_audio"] = {
            "first_pcm_s": round(first, 3),
            "mp3_ready_s": round(time.monotonic() - start, 3),
            "bytes": args.voice_output.stat().st_size,
            "played": False,
            "uploaded": False,
        }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

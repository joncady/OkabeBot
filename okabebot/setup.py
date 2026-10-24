"""Download the configured local speech model once, before starting the bridge."""

import argparse
import os
from pathlib import Path
from .config import get_config, state_dir


def download_model():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    args = parser.parse_args()
    if args.config:
        os.environ["OKABEBOT_CONFIG"] = str(Path(args.config).expanduser().resolve())
        get_config.cache_clear()
    from faster_whisper import WhisperModel

    settings = get_config()["transcription"]
    WhisperModel(
        settings["model"],
        device="cpu",
        compute_type=settings["compute_type"],
        download_root=str(state_dir() / "models"),
    )
    print("Speech model ready.")


if __name__ == "__main__":
    download_model()

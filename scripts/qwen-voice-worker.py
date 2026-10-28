"""Optional Apple Silicon speech worker. References stay in a private manifest."""

import argparse
import json
import math
import os
from pathlib import Path
import socket
import struct
import time
import signal
import threading


def load_references(path):
    """Normalize private references once; generation has no character-specific branches."""
    path = Path(path)
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Provide character references")
    references = {}
    for character, value in raw.items():
        if not isinstance(value, dict) or set(value) - {"audio", "text", "mode", "temperature"}:
            raise ValueError("Unknown reference options")
        mode = value.get("mode", "icl")
        if mode not in ("icl", "speaker_only") or not isinstance(value.get("audio"), str):
            raise ValueError("Choose ICL or speaker-only conditioning and an audio path")
        audio = (path.parent / value["audio"]).resolve()
        text = value.get("text")
        if not audio.is_file() or (
            mode == "icl" and (not isinstance(text, str) or not text.strip())
        ):
            raise ValueError("ICL needs audio and its transcript; speaker-only needs audio")
        if mode == "speaker_only" and text is not None:
            raise ValueError("Speaker-only references must omit the transcript")
        options = {"ref_audio": str(audio), "ref_text": text if mode == "icl" else None}
        if "temperature" in value:
            temperature = value["temperature"]
            if (
                type(temperature) not in (int, float)
                or not math.isfinite(temperature)
                or not 0 <= temperature <= 1
            ):
                raise ValueError("Reference temperature must be between zero and one")
            options["temperature"] = temperature
        references[character] = options
    return references


def main():
    parent_pid = os.environ.get("OKABEBOT_PARENT_PID")
    if parent_pid:

        def watch_parent():
            while os.getppid() == int(parent_pid):
                time.sleep(2)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=watch_parent, daemon=True).start()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--model", default="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit")
    parser.add_argument(
        "--revision", help="Pin the model repository revision for reproducible setup"
    )
    args = parser.parse_args()
    # Install mlx-audio in a separate environment; the controller needs no MLX dependency.
    import mlx.core as mx
    import numpy as np
    from mlx_audio.tts.utils import load_model

    manifest = load_references(args.manifest)
    model_path = args.model
    if args.revision:
        from huggingface_hub import snapshot_download

        model_path = snapshot_download(
            args.model,
            revision=args.revision,
            allow_patterns=["*.json", "*.safetensors", "*.txt", "speech_tokenizer/*"],
        )
    model = load_model(model_path)
    mx.eval(model.parameters())

    def generate(text, character):
        yield from model.generate(
            text=text,
            **manifest[character],
            lang_code="English",
            max_tokens=375,
            stream=True,
            streaming_interval=0.32,
            verbose=False,
        )

    for character in manifest:
        for result in generate("Hello. I am ready.", character):
            mx.eval(result.audio)
        print("WARM", character, flush=True)

    args.socket.parent.mkdir(parents=True, exist_ok=True)
    # Never unlink a live worker's endpoint.
    if args.socket.exists():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            try:
                probe.connect(str(args.socket))
            except ConnectionRefusedError:
                args.socket.unlink()
            else:
                raise RuntimeError("A speech worker is already listening")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(args.socket))
        os.chmod(args.socket, 0o600)
        server.listen(2)
        print("READY", str(args.socket), flush=True)
        try:
            while True:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(30)
                    try:
                        raw = bytearray()
                        while not raw.endswith(b"\n"):
                            byte = connection.recv(1)
                            if not byte or len(raw) > 8192:
                                raise ValueError("Invalid speech request")
                            raw.extend(byte)
                        request = json.loads(raw)
                        if request.get("op") == "status":
                            payload = json.dumps(
                                {
                                    "ready": True,
                                    "characters": list(manifest),
                                    "sample_rate": 24000,
                                    "conditioning": {
                                        key: "speaker_only" if value["ref_text"] is None else "icl"
                                        for key, value in manifest.items()
                                    },
                                }
                            ).encode()
                            connection.sendall(
                                struct.pack("!I", len(payload)) + payload + struct.pack("!I", 0)
                            )
                            continue
                        text, character = request.get("text"), request.get("character")
                        if (
                            not isinstance(text, str)
                            or not text.strip()
                            or len(text) > 600
                            or character not in manifest
                        ):
                            raise ValueError("Invalid text or missing character reference")
                        start = time.perf_counter()
                        count = 0
                        for result in generate(text, character):
                            mx.eval(result.audio)
                            if result.sample_rate != 24000:
                                raise ValueError("Expected 24 kHz audio")
                            audio = np.asarray(result.audio, dtype=np.float32)
                            pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
                            count += len(pcm)
                            if count > 30 * 48000:
                                raise ValueError("Speech exceeded 30 seconds")
                            for offset in range(0, len(pcm), 48000):
                                chunk = pcm[offset : offset + 48000]
                                connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                        connection.sendall(struct.pack("!I", 0))
                        print(
                            "DONE",
                            character,
                            round(time.perf_counter() - start, 3),
                            "seconds",
                            count // 2,
                            "samples",
                            flush=True,
                        )
                    except Exception as exc:
                        # Close an incomplete stream; clients abort rather than replay it.
                        print("ERROR", type(exc).__name__, str(exc), flush=True)
        finally:
            args.socket.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

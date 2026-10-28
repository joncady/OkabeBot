"""Opt-in private Unix-socket conversation adapter, without household tools."""

import base64
import io
import json
import os
from pathlib import Path
import shutil
import socket
import socketserver
import stat
import subprocess
import threading
import time
import wave


LIMIT = 2_000_000


def encode_mp3(pcm, deadline):
    executable = shutil.which("ffmpeg")
    if not executable:
        import imageio_ffmpeg

        executable = imageio_ffmpeg.get_ffmpeg_exe()
    remaining = deadline - time.time()
    if remaining <= 0:
        raise TimeoutError("Encoding deadline expired")
    wav = io.BytesIO()
    with wave.open(wav, "wb") as output:
        output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        output.writeframes(pcm)
    result = subprocess.run(
        [
            executable,
            "-nostdin",
            "-v",
            "error",
            "-i",
            "pipe:0",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "48k",
            "-f",
            "mp3",
            "pipe:1",
        ],
        input=wav.getvalue(),
        capture_output=True,
        check=True,
        timeout=remaining,
    )
    if not 100 < len(result.stdout) < LIMIT:
        raise ValueError("Invalid generated audio size")
    return result.stdout


def render(model, text, session, character, deadline, *, pcm=None, encode=encode_mp3):
    progress = {"stage": "model"}
    started = time.monotonic()
    try:
        return _render(
            model, text, session, character, deadline, pcm=pcm, encode=encode, progress=progress
        )
    except Exception as exc:
        # Carry only a fixed stage and elapsed time across the private RPC. Never
        # expose exception messages, recognized speech or generated text in logs.
        exc.alexa_stage = progress["stage"]
        exc.alexa_elapsed_s = round(time.monotonic() - started, 3)
        raise


def _render(model, text, session, character, deadline, *, pcm, encode, progress):
    from . import speech

    started = time.monotonic()
    answer = model.compose_alexa(text, session, character, deadline)
    answer["audio_ready"] = False
    answer["timings"] = {"model_s": round(time.monotonic() - started, 3)}
    if not answer["audio_safe"]:
        return answer
    progress["stage"] = "synthesis"
    generate = pcm or speech.local_pcm_chunks
    first, chunks, count = None, [], 0
    voice_started = time.monotonic()
    for chunk in generate(
        answer["text"],
        "neutral",
        character["default_voice"],
        character=character["style"],
        deadline=deadline,
    ):
        if time.time() >= deadline:
            raise TimeoutError("Speech deadline expired")
        if not isinstance(chunk, bytes) or len(chunk) % 2:
            raise ValueError("Invalid generated PCM")
        count += len(chunk)
        if count > 20 * 48000:
            raise ValueError("Reply audio is too long")
        if first is None:
            first = time.monotonic() - voice_started
        chunks.append(chunk)
    if not count:
        raise ValueError("No generated audio")
    answer["timings"].update(
        first_pcm_s=round(first, 3), synthesis_s=round(time.monotonic() - voice_started, 3)
    )
    encoding_started = time.monotonic()
    progress["stage"] = "encoding"
    clip = encode(b"".join(chunks), deadline)
    if time.time() >= deadline:
        raise TimeoutError("Audio missed its deadline")
    answer["timings"].update(
        encoding_s=round(time.monotonic() - encoding_started, 3),
        local_total_s=round(time.monotonic() - started, 3),
    )
    answer.update(
        audio_ready=True,
        mp3=base64.b64encode(clip).decode(),
        audio_duration_ms=round(count / 48),
    )
    return answer


class LocalConversationServer:
    """Only this user's local processes may submit tool-free inference requests."""

    def __init__(self, path, model, profile, *, renderer=render):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.stat().st_mode & 0o077:
            raise PermissionError("Conversation socket requires a private directory")
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise PermissionError("Refusing to replace a non-owned socket")
            with socket.socket(socket.AF_UNIX) as probe:
                probe.settimeout(0.2)
                try:
                    probe.connect(str(self.path))
                except ConnectionRefusedError:
                    self.path.unlink()
                else:
                    raise ValueError("Conversation adapter is already running")

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(2)
                try:
                    raw = self.rfile.readline(8193)
                    if len(raw) > 8192 or not raw.endswith(b"\n"):
                        raise ValueError("Invalid local request")
                    value = json.loads(raw)
                    if set(value) != {"text", "session", "deadline"}:
                        raise ValueError("Invalid local operation")
                    deadline = value["deadline"]
                    if type(deadline) not in (float, int) or not 0 < deadline - time.time() <= 8:
                        raise ValueError("Invalid local deadline")
                    result = renderer(model, value["text"], value["session"], profile(), deadline)
                    data = json.dumps(result).encode()
                    if len(data) > LIMIT:
                        raise ValueError("Reply too large")
                except Exception as exc:
                    error = {"error": type(exc).__name__}
                    stage = getattr(exc, "alexa_stage", None)
                    if stage in ("model", "synthesis", "encoding"):
                        error.update(stage=stage, elapsed_s=exc.alexa_elapsed_s)
                    data = json.dumps(error).encode()
                try:
                    self.wfile.write(data + b"\n")
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        self.server = Server(str(self.path), Handler)
        self.path.chmod(0o600)
        self.inode = self.path.stat().st_ino
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        try:
            if self.path.lstat().st_ino == self.inode:
                self.path.unlink()
        except FileNotFoundError:
            pass


def local_request(path, request):
    remaining = request["deadline"] - time.time()
    if not 0 < remaining <= 8:
        raise TimeoutError("Conversation deadline expired")
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(remaining)
        connection.connect(str(path))
        connection.sendall(
            json.dumps({k: request[k] for k in ("text", "session", "deadline")}).encode() + b"\n"
        )
        with connection.makefile("rb") as source:
            raw = source.readline(LIMIT + 2)
        if len(raw) > LIMIT or not raw.endswith(b"\n"):
            raise ValueError("Invalid local response")
        return json.loads(raw)

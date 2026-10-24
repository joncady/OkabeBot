"""Python 3.7-compatible display/BLE service; listens on loopback only."""

import base64
import io
import json
import queue
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tkinter as tk
from PIL import Image
from bot import Bot
from presses import PressController
from camera import Camera
import pip_face
from device_config import load
import math

ROOT = Path(__file__).resolve().parent


class Display:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Hardware Lab")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="black", cursor="none")
        self.label = tk.Label(self.root, bg="black", borderwidth=0)
        self.label.pack(fill="both", expand=True)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.canvas = tk.Canvas(self.root, bg="#101e25", highlightthickness=0)
        self.character = None
        self.queue = queue.Queue()
        self.state = {"kind": "idle", "text": "", "title": "", "revision": 0}
        self.timer = None
        self.photo = None
        self.png = b""
        self.clear()
        self.root.after(50, self.drain)
        self.root.after(80, self.animate)

    def clear(self):
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.state = {
            "kind": "idle",
            "title": "",
            "text": "",
            "revision": self.state["revision"] + 1,
        }
        self.show_image(Image.new("RGB", (480, 320), "#101923"))

    def show_image(self, img):
        self.character = None
        self.canvas.place_forget()
        canonical = io.BytesIO()
        img.save(canonical, format="PNG")
        self.png = canonical.getvalue()
        screen = img.resize(
            (self.root.winfo_screenwidth(), self.root.winfo_screenheight()), Image.BICUBIC
        )
        buf = io.BytesIO()
        screen.save(buf, format="PNG")
        self.photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))
        self.label.configure(image=self.photo)

    def set_character(self, data):
        emotion = data.get("emotion", (self.character or {}).get("emotion", "neutral"))
        activity = data.get("activity", "idle")
        intensity = data.get("intensity", 0.6)
        envelope = data.get("envelope", [])
        start = data.get("start_at", time.time())
        if emotion not in pip_face.EMOTIONS or activity not in pip_face.ACTIVITIES:
            raise ValueError("Unknown emotion or activity")
        if (
            not isinstance(intensity, (float, int))
            or not math.isfinite(intensity)
            or not 0 <= intensity <= 1
        ):
            raise ValueError("intensity must be 0–1")
        if (
            not isinstance(envelope, list)
            or len(envelope) > 600
            or any(
                not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1
                for v in envelope
            )
        ):
            raise ValueError("Invalid mouth envelope")
        if (
            not isinstance(start, (int, float))
            or not math.isfinite(start)
            or abs(start - time.time()) > 15
        ):
            raise ValueError("Invalid start time; check Pi clock")
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        style = data.get("style", "okabe")
        if style not in ("okabe", "pip"):
            raise ValueError("Unknown character style")
        palette = data.get("palette", {})
        if not isinstance(palette, dict) or any(
            k not in ("background", "shell", "accent")
            or not isinstance(v, str)
            or not re.fullmatch(r"#[0-9a-fA-F]{6}", v)
            for k, v in palette.items()
        ):
            raise ValueError("Invalid character palette")
        self.character = dict(
            style=style,
            palette=palette,
            emotion=emotion,
            intensity=intensity,
            activity=activity,
            envelope=envelope,
            started=time.monotonic() + start - time.time(),
        )
        self.state = dict(
            kind="character",
            emotion=emotion,
            activity=activity,
            intensity=intensity,
            revision=self.state["revision"] + 1,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        return self.status()

    def face_args(self):
        data = self.character
        elapsed = time.monotonic() - data["started"]
        index = int(max(0, elapsed) * 20)
        mouth = data["envelope"][index] if elapsed >= 0 and index < len(data["envelope"]) else 0
        if data["activity"] == "speaking" and elapsed >= len(data["envelope"]) / 20:
            data["activity"] = "idle"
            self.state["activity"] = "idle"
        return dict(
            emotion=data["emotion"],
            intensity=data["intensity"],
            mouth=mouth,
            phase=time.monotonic(),
            activity=data["activity"],
            style=data["style"],
            palette=data["palette"],
        )

    def animate(self):
        if self.character:
            self.canvas.delete("all")
            sx, sy = self.root.winfo_screenwidth() / 480, self.root.winfo_screenheight() / 320
            for kind, xy, color, width in pip_face.shapes(**self.face_args()):
                coords = [v * (sx if i % 2 == 0 else sy) for i, v in enumerate(xy)]
                method = (
                    self.canvas.create_oval
                    if kind == "ellipse"
                    else getattr(self.canvas, "create_" + kind)
                )
                options = {"fill": color}
                if kind == "line":
                    options["width"] = width * sx
                else:
                    options["outline"] = ""
                method(*coords, **options)
        self.root.after(80, self.animate)

    def apply(self, data):
        duration = data.get("duration_seconds", 0)
        if not isinstance(duration, (int, float)) or not 0 <= duration <= 86400:
            raise ValueError("Duration must be between 0 and 86400 seconds")
        raw = base64.b64decode(data["png_base64"], validate=True)
        with Image.open(io.BytesIO(raw)) as img:
            if img.format != "PNG" or img.size != (480, 320):
                raise ValueError("Expected a 480x320 PNG")
            img = img.convert("RGB")
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.show_image(img)
        self.state = {
            "kind": data.get("kind", "image"),
            "title": data.get("title", ""),
            "text": data.get("text", ""),
            "revision": self.state["revision"] + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": duration,
        }
        if duration:
            self.timer = self.root.after(int(duration * 1000), self.clear)
        return self.status()

    def status(self):
        return dict(
            self.state,
            canvas_size=[480, 320],
            output_size=[self.root.winfo_screenwidth(), self.root.winfo_screenheight()],
        )

    def drain(self):
        try:
            while True:
                data, reply = self.queue.get_nowait()
                try:
                    op = data["op"]
                    if op == "display":
                        result = self.apply(data)
                    elif op == "clear":
                        self.clear()
                        result = self.status()
                    elif op == "character":
                        result = self.set_character(data)
                    elif op == "preview":
                        if self.character:
                            buf = io.BytesIO()
                            pip_face.render(**self.face_args()).save(buf, format="PNG")
                            self.png = buf.getvalue()
                        result = {"png_base64": base64.b64encode(self.png).decode("ascii")}
                    else:
                        result = self.status()
                    reply.put(result)
                except Exception as exc:
                    reply.put({"error": str(exc)})
        except queue.Empty:
            pass
        self.root.after(50, self.drain)

    def request(self, data):
        reply = queue.Queue(maxsize=1)
        self.queue.put((data, reply))
        return reply.get(timeout=8)


def main():
    display = Display()
    bot = Bot()
    presses = PressController(ROOT / "presses.sqlite3", bot)
    camera = Camera(ROOT / "recordings")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if self.path != "/rpc" or not 0 < size <= 2_000_000:
                    raise ValueError("Invalid request")
                data = json.loads(self.rfile.read(size))
                op = data.get("op")
                if op == "press":
                    result = presses.press(data.get("request_id"))
                elif op == "bot_status":
                    with presses.lock:
                        result = bot.status()
                elif op in ("camera_photo", "camera_record"):
                    result = camera.capture(
                        video=op == "camera_record",
                        duration_seconds=data.get("duration_seconds", 5),
                        low_light=data.get("low_light", False),
                    )
                elif op in ("display", "clear", "status", "preview", "character"):
                    result = display.request(data)
                else:
                    raise ValueError("Unknown operation")
            except Exception as exc:
                result = {"error": str(exc)}
            output = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)

    server = ThreadingHTTPServer(("127.0.0.1", load()["display_port"]), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    display.root.mainloop()


if __name__ == "__main__":
    main()

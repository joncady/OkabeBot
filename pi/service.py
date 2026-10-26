"""Python 3.7-compatible display/BLE service; listens on loopback only."""

import base64
import io
import json
import queue
import uuid
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
import scene
import layout
import reactions
import prop_art
from device_config import load
import math

ROOT = Path(__file__).resolve().parent


class Display:
    def __init__(self):
        self.session_id = uuid.uuid4().hex
        self.root = tk.Tk()
        self.root.title("Hardware Lab")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="black", cursor="none")
        self.label = tk.Label(self.root, bg="black", borderwidth=0)
        self.label.pack(fill="both", expand=True)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.canvas = tk.Canvas(self.root, bg="#101e25", highlightthickness=0)
        self.scene_items = []
        self.notification_item = None
        self.media_panel = None
        self.media_key = None
        self.sport_items = []
        self.sport_key = None
        self.media_shown = False
        self.media_offset = None
        self.progress_coords = None
        self.progress_visible = None
        self.frame_period = 0
        self.frame_work = 0
        self.frame_started = None
        self.character = None
        self.notification = None
        self.notification_until = 0
        self.card_photo = None
        self.deploying = False
        self.music = {}
        self.music_scroll_since = time.monotonic()
        self.music_preview_until = 0
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
            or not -35 <= start - time.time() <= 15
        ):
            raise ValueError("Invalid start time; check Pi clock")
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        style = data.get("style", (self.character or {}).get("style", "okabe"))
        if style not in ("okabe", "kurisu", "pip", "sonic"):
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

    def set_notification(self, data):
        value = data.get("notification")
        duration = data.get("duration_seconds", 12)
        if not isinstance(duration, (int, float)) or not 1 <= duration <= 120:
            raise ValueError("Notification duration must be 1–120 seconds")
        if value is not None:
            if not isinstance(value, dict) or any(
                not isinstance(value.get(k, ""), str) or len(value.get(k, "")) > limit
                for k, limit in (("title", 100), ("body", 500), ("source", 30))
            ):
                raise ValueError("Invalid notification")
            if not self.character:
                self.set_character({})
        self.notification = value
        self.notification_until = time.monotonic() + duration
        overlay = scene.card(value, style=(self.character or {}).get("style")).resize(
            (self.root.winfo_screenwidth(), self.root.winfo_screenheight()), Image.NEAREST
        )
        buf = io.BytesIO()
        overlay.save(buf, format="PNG")
        self.card_photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))
        return self.status()

    def cache_crest(self, data):
        key = data.get("key", "")
        if not isinstance(key, str) or not re.fullmatch(r"wiki_q[0-9]+", key):
            raise ValueError("Invalid crest key")
        encoded = data.get("png_base64", "")
        if not isinstance(encoded, str) or len(encoded) > 50000:
            raise ValueError("Crest is too large")
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.format != "PNG" or not (1 <= im.width <= 64 and 1 <= im.height <= 64):
                raise ValueError("Crest must be PNG up to 64px")
            im.load()
        path = ROOT / "assets" / "crests" / (key + ".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != raw:
            temp = path.with_suffix(".tmp")
            temp.write_bytes(raw)
            temp.replace(path)
            reactions.badge.cache_clear()
            reactions.badge_runs.cache_clear()
        return {"ok": True, "key": key}

    def set_music(self, data):
        value = data.get("music", {})
        if not isinstance(value, dict) or type(value.get("is_playing", False)) is not bool:
            raise ValueError("Invalid music state")
        for key in ("title", "artist", "device"):
            if not isinstance(value.get(key, ""), str) or len(value.get(key, "")) > 500:
                raise ValueError("Invalid music metadata")

        def title_key(item):
            video = item.get("video") or {}
            return (video.get("app"), video.get("title"), item.get("title"), item.get("artist"))

        if title_key(value) != title_key(self.music):
            self.music_scroll_since = time.monotonic()
        video = value.get("video")
        if video:
            video["position_received_at"] = time.monotonic()
        preview = value.get("preview_seconds", 0)
        if type(preview) not in (int, float) or not 0 <= preview <= 120:
            raise ValueError("Preview must be 0–120 seconds")
        self.music_preview_until = time.monotonic() + preview if preview else 0
        self.music = value
        if value.get("is_playing") and not self.character:
            self.set_character({})
        return self.status()

    def face_args(self):
        data = self.character
        now = time.monotonic()
        if (
            data["activity"] != "idle"
            or self.notification
            or self.music.get("is_playing")
            or self.deploying
        ):
            self.idle_since = now
        if not hasattr(self, "idle_since"):
            self.idle_since = now
        elapsed = time.monotonic() - data["started"]
        index = int(max(0, elapsed) * 20)
        mouth = data["envelope"][index] if elapsed >= 0 and index < len(data["envelope"]) else 0
        if data["activity"] == "speaking" and elapsed >= len(data["envelope"]) / 20:
            data["activity"] = "idle"
            self.state["activity"] = "idle"
        return dict(
            idle_seconds=max(0, now - self.idle_since),
            emotion=data["emotion"],
            intensity=data["intensity"],
            mouth=mouth,
            phase=time.monotonic(),
            activity=data["activity"],
            style=data["style"],
            palette=data["palette"],
        )

    def draw_scene(self, shapes, sx, sy):
        # Retain Tk items so static crest pixels do not get deleted/redrawn.
        kinds = tuple(shape[0] for shape in shapes)
        self.scene_rebuilt = False
        if kinds != tuple(item[0] for item in self.scene_items):
            for item in self.scene_items:
                self.canvas.delete(item[1])
            self.scene_rebuilt = True
            self.scene_items = []
            for kind, xy, color, width in shapes:
                method = (
                    self.canvas.create_oval
                    if kind == "ellipse"
                    else getattr(self.canvas, "create_" + kind)
                )
                coords = tuple(round(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate(xy))
                options = {"fill": color}
                options.update({"width": width * sx} if kind == "line" else {"outline": ""})
                identifier = method(*coords, **options)
                self.scene_items.append((kind, identifier, coords, color, width * sx))
            return
        for i, (kind, xy, color, width) in enumerate(shapes):
            previous = self.scene_items[i]
            coords = tuple(round(v * (sx if n % 2 == 0 else sy)) for n, v in enumerate(xy))
            if coords != previous[2]:
                self.canvas.coords(previous[1], *coords)
            options = {}
            if color != previous[3]:
                options["fill"] = color
            if kind == "line" and width * sx != previous[4]:
                options["width"] = width * sx
            if options:
                self.canvas.itemconfigure(previous[1], **options)
            self.scene_items[i] = (kind, previous[1], coords, color, width * sx)

    def draw_content_assets(self, now, sx, sy):
        video = self.music.get("video") or {}
        active = reactions.active(
            self.music, self.notification, self.character.get("activity", "idle"), self.deploying
        )
        reaction = video.get("reaction") or {}
        teams = reaction.get("participants", [])[:2] if active else []
        art_key = prop_art.key(reaction) if active and reaction and prop_art.available() else None
        key = (json.dumps(teams, sort_keys=True), art_key, sx, sy)
        if key != self.sport_key:
            for item in self.sport_items:
                self.canvas.delete(item)
            self.sport_items = []
            self.prop_coords = None
            self.crest_photos = []
            self.prop_photo = None
            for i, team in enumerate(teams):
                im = reactions.badge(
                    team.get("crest", ""),
                    team.get("short_name", "?"),
                    tuple(team.get("colors", ["#486a81", "#ffffff"])),
                )
                im = im.resize(
                    (max(1, round(layout.CREST_SIZE * sx)), max(1, round(layout.CREST_SIZE * sy))),
                    Image.NEAREST,
                )
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))
                self.crest_photos.append(photo)
                self.sport_items.append(
                    self.canvas.create_image(
                        (layout.CREST_X + i * layout.CREST_STEP) * sx,
                        layout.CREST_Y * sy,
                        image=photo,
                        anchor="nw",
                    )
                )
            if art_key:
                _, _, w, h = prop_art.SLOT
                im = prop_art.sprite(art_key).resize(
                    (max(1, round(w * sx)), max(1, round(h * sy))), Image.NEAREST
                )
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                self.prop_photo = tk.PhotoImage(
                    data=base64.b64encode(buf.getvalue()).decode("ascii")
                )
                self.prop_item = self.canvas.create_image(0, 0, anchor="nw", image=self.prop_photo)
                self.sport_items.append(self.prop_item)
            self.sport_key = key
        if self.prop_photo:
            x, y, _, _ = prop_art.position(now, video.get("state"))
            coords = (round(x * sx), round(y * sy))
            if coords != self.prop_coords:
                self.canvas.coords(self.prop_item, *coords)
                self.prop_coords = coords
        if self.scene_rebuilt:
            for item in self.sport_items:
                self.canvas.tag_raise(item)

    def draw_media(self, now, sx, sy):
        if self.media_panel is None:
            self.media_panel = tk.Canvas(self.canvas, bg="#172b34", highlightthickness=0)
            self.media_title = tk.Canvas(self.media_panel, bg="#172b34", highlightthickness=0)
            self.media_title_item = self.media_title.create_image(0, 0, anchor="nw")
            self.media_icon_item = self.media_panel.create_image(0, 0, anchor="nw")
            self.media_track = self.media_panel.create_rectangle(
                0, 0, 0, 0, fill="#38444b", outline=""
            )
            self.media_progress = self.media_panel.create_rectangle(
                0, 0, 0, 0, fill="#f04444", outline=""
            )
        video = self.music.get("video")
        title = (
            video.get("title", "")
            if video
            else "{} · {}".format(self.music.get("title", "Music"), self.music.get("artist", ""))
        )
        left, viewport = (layout.MEDIA_LEFT, layout.MEDIA_VIEWPORT)
        key = (title, left, viewport, (video or {}).get("app"), sx, sy)
        if key != self.media_key:
            strip, self.media_travel = scene.media_title_strip(title, None, viewport)
            strip = strip.resize(
                (max(1, round(strip.width * sx)), max(1, round(strip.height * sy))), Image.NEAREST
            )
            buf = io.BytesIO()
            strip.save(buf, format="PNG")
            self.media_title_photo = tk.PhotoImage(
                data=base64.b64encode(buf.getvalue()).decode("ascii")
            )
            self.media_title.itemconfigure(self.media_title_item, image=self.media_title_photo)
            self.media_title.place(
                x=round(left * sx),
                y=round(layout.MEDIA_TITLE_Y * sy),
                width=round(viewport * sx),
                height=round(layout.MEDIA_TITLE_HEIGHT * sy),
            )
            if video or self.music.get("is_playing"):
                app = video.get("app", "") if video else "Spotify"
                icon = scene.icon(scene.media_source(app), layout.MEDIA_ICON_SIZE)
                icon = icon.resize(
                    (
                        max(1, round(layout.MEDIA_ICON_SIZE * sx)),
                        max(1, round(layout.MEDIA_ICON_SIZE * sy)),
                    ),
                    Image.NEAREST,
                )
                buf = io.BytesIO()
                icon.save(buf, format="PNG")
                self.media_icon_photo = tk.PhotoImage(
                    data=base64.b64encode(buf.getvalue()).decode("ascii")
                )
                self.media_panel.itemconfigure(
                    self.media_icon_item, image=self.media_icon_photo, state="normal"
                )
                self.media_panel.coords(
                    self.media_icon_item, layout.MEDIA_ICON_X * sx, layout.MEDIA_ICON_Y * sy
                )
            else:
                self.media_panel.itemconfigure(self.media_icon_item, state="hidden")
            self.media_key = key
            self.media_offset = None
            self.media_shown = False
            self.progress_visible = None
            self.progress_coords = None
        # Move only when the next physical pixel changes.
        offset = round(scene.marquee_offset(self.media_travel, now - self.music_scroll_since) * sx)
        if offset != self.media_offset:
            self.media_title.coords(self.media_title_item, -offset, 0)
            self.media_offset = offset
        fraction = scene.progress_fraction(video, now)
        visible = fraction is not None
        if visible != self.progress_visible:
            for identifier in (self.media_track, self.media_progress):
                self.media_panel.itemconfigure(identifier, state="normal" if visible else "hidden")
            self.media_panel.coords(
                self.media_track,
                20 * sx,
                layout.MEDIA_PROGRESS_Y * sy,
                460 * sx,
                (layout.MEDIA_PROGRESS_Y + 3) * sy,
            )
            self.progress_visible = visible
        if visible:
            coords = (
                round(20 * sx),
                round(layout.MEDIA_PROGRESS_Y * sy),
                round((20 + 440 * fraction) * sx),
                round((layout.MEDIA_PROGRESS_Y + 3) * sy),
            )
            if coords != self.progress_coords:
                self.media_panel.coords(self.media_progress, *coords)
                self.progress_coords = coords
        if not self.media_shown:
            self.media_panel.place(
                x=0,
                y=round(layout.MEDIA_TOP * sy),
                width=round(480 * sx),
                height=round(layout.MEDIA_HEIGHT * sy),
            )
            self.media_shown = True

    def animate(self):
        started = time.monotonic()
        if self.frame_started is not None:
            period = started - self.frame_started
            self.frame_period = (
                period if not self.frame_period else 0.9 * self.frame_period + 0.1 * period
            )
        self.frame_started = started
        if self.music_preview_until and started >= self.music_preview_until:
            self.music = {}
            self.music_preview_until = 0
        if self.notification and started >= self.notification_until:
            self.notification = None
        if self.character:
            sx, sy = self.root.winfo_screenwidth() / 480, self.root.winfo_screenheight() / 320
            self.draw_scene(
                scene.shapes(
                    notification=self.notification,
                    deploying=self.deploying,
                    music=self.music,
                    native_sprites=True,
                    **self.face_args(),
                ),
                sx,
                sy,
            )
            self.draw_content_assets(started, sx, sy)
            if self.notification and self.card_photo:
                if self.media_panel:
                    self.media_panel.place_forget()
                    self.media_shown = False
                if self.notification_item is None:
                    self.notification_item = self.canvas.create_image(0, 0, anchor="nw")
                self.canvas.itemconfigure(
                    self.notification_item, image=self.card_photo, state="normal"
                )
                self.canvas.tag_raise(self.notification_item)
            else:
                if self.notification_item:
                    self.canvas.itemconfigure(self.notification_item, state="hidden")
                if self.music.get("is_playing") or self.music.get("video"):
                    self.draw_media(started, sx, sy)
                elif self.media_panel:
                    self.media_panel.place_forget()
                    self.media_shown = False
        work = time.monotonic() - started
        self.frame_work = work if not self.frame_work else 0.9 * self.frame_work + 0.1 * work
        self.root.after(max(1, round((1 / 30 - work) * 1000)), self.animate)

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
            session_id=self.session_id,
            render_metrics={
                "fps": round(1 / self.frame_period, 1) if self.frame_period else 0,
                "work_ms": round(self.frame_work * 1000, 1),
            },
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
                    elif op == "deployments":
                        if type(data.get("active")) is not bool:
                            raise ValueError("active must be boolean")
                        self.deploying = data["active"]
                        result = self.status()
                    elif op == "notification":
                        result = self.set_notification(data)
                    elif op == "music_pulse":
                        level = data.get("level", 0)
                        if type(level) not in (int, float) or not 0 <= level <= 1:
                            raise ValueError("Invalid music level")
                        expression = data.get("expression", "neutral")
                        if expression not in ("neutral", "happy", "excited"):
                            raise ValueError("Invalid music expression")
                        self.music.update(
                            {
                                "expression": expression,
                                "level": level,
                                "meter_active": bool(data.get("active")),
                                "pulse_at": time.monotonic(),
                            }
                        )
                        result = {"ok": True}
                    elif op == "cache_crest":
                        result = self.cache_crest(data)
                    elif op == "music":
                        result = self.set_music(data)
                    elif op == "character":
                        result = self.set_character(data)
                    elif op == "preview":
                        if self.character:
                            buf = io.BytesIO()
                            scene.render(
                                notification=self.notification,
                                deploying=self.deploying,
                                music=self.music,
                                **self.face_args(),
                            ).save(buf, format="PNG")
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
                elif op in (
                    "display",
                    "clear",
                    "status",
                    "preview",
                    "character",
                    "notification",
                    "deployments",
                    "music",
                    "music_pulse",
                    "cache_crest",
                ):
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

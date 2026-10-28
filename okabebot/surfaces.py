"""Acknowledged single-character handoffs between independently rendered surfaces."""

import secrets
import threading
import time
import uuid


class Surfaces:
    DURATION = 1.4
    RECEIVER_LEASE = 6

    def __init__(self, rpc, cast_getter=lambda: None, start=True, cast_resolver=None):
        from .config import get_config

        self.settings = get_config()["surfaces"]
        self.DURATION = self.settings["duration_seconds"]
        from .surface_registry import Registry

        self.registry = Registry()
        self.active_id = next(p["id"] for p in self.settings["locations"] if p["adapter"] == "cast")
        self.direct = None
        self.pending_move = None
        self.base = ""
        self.travel_direction = self.settings["travel_side"]
        self.remote_input = None
        self.rpc, self.cast_getter = rpc, cast_getter
        self.cast_resolver = cast_resolver
        self.lock = threading.RLock()
        self.phase = "pi"
        self.identifier = uuid.uuid4().hex
        self.token = self.preview_token = ""
        self.preview_until = 0
        self.last_seen = self.started = time.monotonic()
        self.ready = False
        self.error = ""
        self.last_renewal = 0
        self.assets = {}
        self.receiver_session = None
        self.receiver_active = False
        self.return_command_sent = False
        self.next_retry = 0
        self.retry_delay = 1
        self.tv_requests = {}
        self.stop = threading.Event()
        if start:
            threading.Thread(target=self._run, daemon=True).start()

    def cast_for(self, identity):
        if self.cast_resolver is not None:
            return self.cast_resolver(identity)
        primary = next(p["id"] for p in self.settings["locations"] if p["adapter"] == "cast")
        return self.cast_getter() if identity == primary else None

    def snapshot(self):
        with self.lock:
            from .config import get_config

            places = self.registry.enrich(self.settings["locations"], include_pending=True)
            home = next(p for p in places if p["adapter"] == "pi")
            away = next((p for p in places if p["id"] == self.active_id), home)
            for place in places:
                if place["adapter"] in ("pi", "cast"):
                    place["available"] = (
                        place["adapter"] == "pi" or self.cast_for(place["id"]) is not None
                    )
            destination = (
                away if self.phase in ("preparing", "leaving_pi", "entering_tv", "tv") else home
            )
            result = {
                "locations": places,
                "scene_world_enabled": self.registry.scene_world_enabled(),
                "beam_audio_available": bool(get_config()["audio"]["sonos_host"]),
                "return_location": home,
                "current_location": home["id"]
                if self.phase == "pi"
                else away["id"]
                if self.phase == "tv"
                else None,
                "destination_location": destination["id"],
                "destination_name": destination["name"],
                "remote_input": self.remote_input,
                "remote_controls": self.settings["remote_controls"],
                "visibility_lease_seconds": self.RECEIVER_LEASE,
                "lab": dict(self.settings["lab"]),
                "tv_requests": dict(self.tv_requests),
                "phase": self.phase,
                "transition_id": self.identifier,
                "location": "tv"
                if self.phase == "tv"
                else "pi"
                if self.phase == "pi"
                else "moving",
                "error": self.error,
                "tv_side": self.travel_direction,
                "browser_url": self.base + "/companion/",
                "duration_seconds": self.DURATION,
                "receiver_connected": self.ready
                and time.monotonic() - self.last_seen < self.RECEIVER_LEASE,
            }
            from .scene_sets import CATALOG
            from .profiles import current_character

            result["scene_catalog"] = CATALOG
            result["character_style"] = current_character()["style"]
            if self.direct:
                transfer = self.direct
                target = next((p for p in places if p["id"] == transfer.target_id), home)
                result.update(
                    destination_location=target["id"],
                    destination_name=target["name"],
                    current_location=transfer.source_id if transfer.stage == "preparing" else None,
                    direct_transfer={
                        "source": transfer.source_id,
                        "target": transfer.target_id,
                        "stage": transfer.stage,
                    },
                )
            return result

    def ensure_scene(self, location_id, style=None):
        if not self.registry.scene_world_enabled():
            from .locations import configured

            if any(p["id"] == location_id and p["adapter"] == "alexa" for p in configured()):
                raise ValueError("Set up scene world before moving to an Alexa destination")
            return
        from .scene_sets import environment
        from .profiles import current_character

        places = self.registry.enrich(self.settings["locations"])
        home = next(p for p in places if p["adapter"] == "pi")
        place = next((p for p in places if p["id"] == location_id), None)
        character = style or current_character()["style"]
        if (
            place is not None
            and place.get("supported_scenes") is not None
            and character not in place["supported_scenes"]
        ):
            raise ValueError("That character is not supported by this destination")
        if not environment(home, character)["assigned"]:
            raise ValueError("Assign a home scene for this character before moving or switching")
        if place is None or not environment(place, character)["assigned"]:
            raise ValueError("Assign a unique scene set to that location in the dashboard first")
        supported = place.get("supported_scenes")
        if supported is not None and environment(place, character)["set"] not in supported.get(
            character, []
        ):
            raise ValueError("That character/set is not supported by this destination")

    def move(self, location_id, base):
        from .locations import configured

        place = next((p for p in configured() if p["id"] == location_id), None)
        if place is None:
            raise ValueError("Unknown destination; list companion locations first")
        self.ensure_scene(location_id)
        with self.lock:
            self.base = base
            target = "pi" if place["adapter"] == "pi" else "tv"
            if self.phase == target and (target == "pi" or self.active_id == location_id):
                return dict(self.snapshot(), accepted=False, already_there=True)
            if target == "pi":
                self.pending_move = None
                return dict(self.return_home(), accepted=True)
            if place["adapter"] in ("browser", "mac", "alexa"):
                if not any(
                    p["id"] == location_id and p.get("available") for p in self.registry.list()
                ):
                    raise ValueError("Open the destination screen before moving there")
            if self.direct:
                raise ValueError("Wait until the current movement finishes")
            if self.phase == "tv":
                from .surface_transfer import DirectTransfer

                return dict(DirectTransfer(self, place, base).start(), accepted=True)
            if self.phase != "pi":
                self.pending_move = (location_id, base)
                self.return_home()
                return dict(self.snapshot(), accepted=True)
            self.active_id = location_id
            home = next(p for p in configured() if p["adapter"] == "pi")
            self.travel_direction = self.registry.direction(
                home["id"], location_id, self.settings["locations"]
            )
            if place["adapter"] == "cast":
                result = (
                    self.begin(base, location_id=location_id)
                    if location_id
                    != next(p["id"] for p in self.settings["locations"] if p["adapter"] == "cast")
                    else self.begin(base)
                )
            else:
                result = self.begin(base, launch=False)
            return {k: v for k, v in dict(result, accepted=True).items() if k != "url"}

    def registered(self, token):
        try:
            return self.registry.device(token)
        except (PermissionError, ValueError):
            return None

    def receiver_token(self, token):
        item = self.registered(token)
        if item:
            if item["id"] != self.active_id:
                raise PermissionError("This screen is not the active destination")
            return self.token
        return token

    def layout(self, data):
        with self.lock:
            if data.get("initialize_scenes") is True:
                if set(data) != {"initialize_scenes"}:
                    raise ValueError("Scene initialization cannot include other layout edits")
                if self.phase != "pi" or self.direct:
                    raise ValueError("Return the character home before initializing scene sets")
                self.registry.initialize_scenes(self.settings["locations"])
                return self.snapshot()
            choices = data.get("scene_selections")
            home = next(p["id"] for p in self.settings["locations"] if p["adapter"] == "pi")
            if choices is not None and not isinstance(choices, dict):
                raise ValueError("Provide character scene selections")
            if choices:
                if not self.registry.scene_world_enabled():
                    raise ValueError("Set up scene world before editing individual assignments")
                if data.get("id") == home and any(v is None for v in choices.values()):
                    raise ValueError("Keep a home set for each character so it can always return")
                current = self.snapshot()["current_location"]
                from .profiles import current_character

                style = current_character()["style"]
                if self.phase != "pi" and (self.direct or current is None):
                    raise ValueError("Wait for the character to finish moving before editing sets")
                if data.get("id") == current and style in choices:
                    existing = (
                        next(
                            p
                            for p in self.registry.enrich(self.settings["locations"])
                            if p["id"] == current
                        )
                        .get("scene_selections", {})
                        .get(style)
                    )
                    if existing and choices[style] != existing:
                        raise ValueError(
                            "Move the character elsewhere before changing its current set"
                        )
            if data.get("audio_target") == "beam":
                from .config import get_config

                if not get_config()["audio"]["sonos_host"]:
                    raise ValueError("Configure a Sonos speaker first")
            self.registry.update(data.get("id"), data, self.settings["locations"])
            if data.get("remove") is True or data.get("approved") is False:
                if self.pending_move and self.pending_move[0] == data.get("id"):
                    self.pending_move = None
                if self.direct and self.direct.target_id == data.get("id"):
                    self.direct.cancel("Destination screen access revoked")
                elif self.active_id == data.get("id") and self.phase != "pi":
                    self._recover("Screen access revoked; returning after its visibility lease")
            return self.snapshot()

    def input(self, token, key):
        if not self.authorized(token, preview=False):
            raise PermissionError("Receiver session expired")
        if key not in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter", "Back"):
            raise ValueError("Unsupported remote key")
        with self.lock:
            self.remote_input = {"key": key, "at": time.time()}
        return {"accepted": True}

    def observe(self, address, path):
        from .config import get_config

        config = get_config()
        if address == config["spotify"]["cast_host"]:
            names = {
                "/tv/": "page",
                "/tv.js": "script",
                "/surfaces/state": "state",
                "/surfaces/assets": "artwork",
                "/surfaces/heartbeat": "heartbeat",
            }
            if path in names:
                with self.lock:
                    key = names[path]
                    self.tv_requests[key] = self.tv_requests.get(key, 0) + 1

    def authorized(self, token, preview=True):
        if self.direct and self.direct.role(token):
            return True
        item = self.registered(token) if token else None
        if item:
            return preview or (item["id"] == self.active_id and bool(self.token))
        return bool(token) and (
            (bool(self.token) and secrets.compare_digest(token, self.token))
            or (
                preview
                and time.monotonic() < self.preview_until
                and bool(self.preview_token)
                and secrets.compare_digest(token, self.preview_token)
            )
        )

    def preview(self, base):
        with self.lock:
            self.preview_token = secrets.token_urlsafe(32)
            self.preview_until = time.monotonic() + 1800
            return {"url": base + "/tv/#" + self.preview_token}

    def begin(self, base, launch=True, location_id=None):
        with self.lock:
            if launch:
                self.active_id = location_id or next(
                    p["id"] for p in self.settings["locations"] if p["adapter"] == "cast"
                )
            if self.phase != "pi":
                raise ValueError("Return the companion to Pi before starting another handoff")
            self.receiver_session = None
            self.receiver_active = False
            self.next_retry, self.retry_delay = 0, 1
            self.identifier, self.token = uuid.uuid4().hex, secrets.token_urlsafe(32)
            self.phase, self.started, self.ready, self.error = (
                "preparing",
                time.monotonic(),
                False,
                "",
            )
            url = base + "/tv/#" + self.token
        if launch:
            threading.Thread(
                target=self._launch, args=(url, None, self.active_id), daemon=True
            ).start()
        return {"url": url, **self.snapshot()}

    def _launch(self, url, direct=None, location_id=None):
        from urllib.parse import urlsplit

        generation = urlsplit(url).fragment
        with self.lock:
            if direct is not None:
                if self.direct is not direct or generation != direct.target_token:
                    return
            elif self.token != generation:
                return
        try:
            from pychromecast.controllers.dashcast import DashCastController

            cast = self.cast_for(direct.target_id if direct else location_id or self.active_id)
            if cast is None:
                raise ValueError(
                    "TV Cast connection unavailable; open the TV receiver URL to test the handoff in a browser"
                )

            from pychromecast.config import APP_DASHCAST

            if cast.status.app_id == APP_DASHCAST:
                # A forced LAUNCH can reuse a navigated-away receiver session.
                # Stop that app once so its JS can accept the new dashboard URL.
                cast.quit_app(timeout=5)

            class FreshDashCast(DashCastController):
                def launch(self, *, callback_function=None, force_launch=False):
                    # force=True in load_url navigates away from DashCast's
                    # receiver JS. A later visit must relaunch that receiver
                    # before it can accept a new URL.
                    return super().launch(callback_function=callback_function, force_launch=True)

            controller = FreshDashCast()
            cast.register_handler(controller)
            controller.load_url(url, force=True)
            # Capture ownership once the launched receiver appears, including
            # a receiver whose page never becomes ready.
            deadline = time.monotonic() + 10
            from pychromecast.config import APP_DASHCAST

            while time.monotonic() < deadline:
                if cast.status.app_id == APP_DASHCAST:
                    with self.lock:
                        if direct is not None:
                            if self.direct is direct:
                                direct.target_session = cast.status.session_id
                        elif self.token == generation:
                            self.receiver_session = cast.status.session_id
                    break
                self.stop.wait(0.1)
        except Exception as exc:
            with self.lock:
                if direct is not None:
                    if self.direct is direct:
                        direct.target_error = str(exc)
                elif self.token == generation:
                    self._recover(str(exc))

    def heartbeat(self, token):
        if not self.authorized(token, preview=False):
            raise PermissionError("Receiver session expired")
        with self.lock:
            if self.direct:
                return self.direct.heartbeat(token)
            self.last_seen, self.ready = time.monotonic(), True
            item = self.registered(token)
            if item:
                self.registry.heartbeat(token)
            cast = self.cast_for(self.active_id)
            if cast and not item:
                from pychromecast.config import APP_DASHCAST

                if cast.status.app_id == APP_DASHCAST:
                    self.receiver_session = cast.status.session_id
                    self.receiver_active |= getattr(cast.status, "is_active_input", None) is True
        return self.snapshot()

    def acknowledge(self, token, kind, identifier):
        with self.lock:
            if self.direct:
                return self.direct.acknowledge(token, kind, identifier)
        token = self.receiver_token(token)
        if not self.authorized(token, preview=False) or identifier != self.identifier:
            raise PermissionError("Stale receiver acknowledgement")
        with self.lock:
            if kind == "entered" and self.phase == "entering_tv":
                self.phase, self.started = "tv", time.monotonic()
            elif kind == "departed" and self.phase == "leaving_tv":
                self._start_return(time.monotonic())
                self._quit_owned_receiver()
        return self.snapshot()

    def return_home(self):
        self.ensure_scene(next(p["id"] for p in self.settings["locations"] if p["adapter"] == "pi"))
        with self.lock:
            if self.direct:
                self.direct.cancel("Returning to companion display")
                if self.phase != "tv":
                    return self.snapshot()
            if self.phase in ("pi", "entering_pi"):
                return self.snapshot()
            if self.phase in ("tv", "entering_tv"):
                home = next(p["id"] for p in self.settings["locations"] if p["adapter"] == "pi")
                try:
                    self.travel_direction = self.registry.direction(
                        home, self.active_id, self.settings["locations"]
                    )
                except KeyError:
                    pass
                self.phase, self.started = "leaving_tv", time.monotonic()
            else:
                self._recover("Returning to Pi")
        return self.snapshot()

    def _quit_owned_receiver(self):
        return self._quit_receiver(self.active_id, self.receiver_session)

    def _quit_receiver(self, location_id, session):
        if not any(
            p["id"] == location_id and p["adapter"] == "cast" for p in self.settings["locations"]
        ):
            return
        cast = self.cast_for(location_id)
        if cast is None:
            return
        from pychromecast.config import APP_DASHCAST

        if cast and cast.status.app_id == APP_DASHCAST and cast.status.session_id == session:
            cast.quit_app()

    def _command(self, phase):
        return {
            "op": "presence",
            "phase": phase,
            "direction": self.travel_direction,
            "transition_id": self.identifier,
            "duration_seconds": self.DURATION,
            "lease_seconds": 12,
        }

    def _start_return(self, now):
        try:
            home = next(p["id"] for p in self.settings["locations"] if p["adapter"] == "pi")
            self.travel_direction = self.registry.direction(
                home, self.active_id, self.settings["locations"]
            )
        except KeyError:
            pass
        self.phase, self.started = "entering_pi", now
        self.token, self.ready = "", False
        self.return_command_sent = False
        self.next_retry, self.retry_delay = 0, 1

    def receiver_closed(self, token, identifier):
        with self.lock:
            if self.direct:
                return self.direct.closed(token, identifier)
        token = self.receiver_token(token)
        if not self.authorized(token, preview=False) or identifier != self.identifier:
            raise PermissionError("Stale receiver close event")
        with self.lock:
            if self.phase == "preparing":
                self.phase, self.token, self.ready = "pi", "", False
            else:
                self._start_return(time.monotonic())
        return self.snapshot()

    def _receiver_gone(self):
        return self._location_gone(self.active_id, self.receiver_session, self.receiver_active)

    def _location_gone(self, location_id, session, active):
        if not any(
            p["id"] == location_id and p["adapter"] == "cast" for p in self.settings["locations"]
        ):
            return False
        cast = self.cast_for(location_id)
        if not cast or not session:
            return False
        from pychromecast.config import APP_DASHCAST

        status = cast.status
        return (
            status.app_id != APP_DASHCAST
            or (status.session_id is not None and status.session_id != session)
            or (active and getattr(status, "is_stand_by", None) is True)
            or (active and getattr(status, "is_active_input", None) is False)
        )

    def _recover(self, message):
        with self.lock:
            if self.direct:
                self._quit_receiver(self.direct.target_id, self.direct.target_session)
                self.direct = None
            now = time.monotonic()
            self.error = message[:240]
            self.token, self.ready = "", False
            if self.phase == "preparing":
                self.phase = "pi"
                self._quit_owned_receiver()
                return
            if self.phase == "entering_pi":
                self.return_command_sent = False
            elif self.phase != "recovering":
                self.phase, self.started = "recovering", now
            self.next_retry = now + self.retry_delay
            self.retry_delay = min(5, self.retry_delay * 2)

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if self.direct:
                self.direct.tick(now)
                return
            phase, identifier = self.phase, self.identifier
            if phase == "pi":
                if self.pending_move:
                    target, base = self.pending_move
                    self.pending_move = None
                    self.move(target, base)
                return
            if now < self.next_retry:
                return
            if phase == "preparing":
                if self.ready:
                    self.rpc(self._command("departing"))
                    self.phase, self.started = "leaving_pi", now
                elif now - self.started > 20:
                    self._recover(
                        "Receiver did not become ready. The companion stayed at its current display."
                    )
                return
            if phase not in ("recovering", "entering_pi") and self._receiver_gone():
                self._start_return(now)
                phase = "entering_pi"
            if (
                phase not in ("recovering", "entering_pi")
                and now - self.last_seen > self.RECEIVER_LEASE
            ):
                self._recover(
                    "Receiver disconnected; waiting for its visibility lease before returning"
                )
                return
            if phase == "recovering":
                if now - self.started <= self.RECEIVER_LEASE + 1:
                    return
                self._start_return(now)
                phase = "entering_pi"
            if phase == "entering_pi":
                if not self.return_command_sent:
                    self.rpc(self._command("arriving"))
                    self.return_command_sent, self.started = True, now
                    return
                state = self.rpc({"op": "status"}).get("presence", {})
                if state.get("transition_id") == identifier and state.get("rendered") == "home":
                    self.phase, self.token, self.ready, self.error = "pi", "", False, ""
                    self.next_retry, self.retry_delay = 0, 1
                elif now - self.started > 15:
                    # Reconcile a reboot or lost acknowledgement with the same
                    # idempotent movement identity, never abandon desired home.
                    self.return_command_sent = False
                    self.error = "Return pending; waiting for the display to confirm arrival"
                return
            if phase == "leaving_pi":
                state = self.rpc({"op": "status"}).get("presence", {})
                if state.get("transition_id") == identifier and state.get("rendered") == "away":
                    self.phase, self.started = "entering_tv", now
                elif now - self.started > 15:
                    self._recover("Display movement acknowledgement timed out")
            elif now - self.last_renewal > 3:
                self.rpc(self._command("away"))
                self.last_renewal = now
            if phase in ("entering_tv", "leaving_tv") and now - self.started > 15:
                self._recover("Receiver animation acknowledgement timed out")

    def _run(self):
        while not self.stop.wait(0.3):
            try:
                self.tick()
            except Exception:
                self._recover("Display unavailable; return remains pending until it reconnects")

    def close(self):
        self.stop.set()

    def character_assets(self, profile, emotion="neutral"):
        key = (profile["style"], emotion, tuple(sorted(profile.get("palette", {}).items())))
        if key not in self.assets:
            result = self.rpc(
                {
                    "op": "character_assets",
                    "style": key[0],
                    "emotion": key[1],
                    "palette": profile.get("palette", {}),
                }
            )
            self.assets[key] = result
            if len(self.assets) > 10:
                self.assets.pop(next(iter(self.assets)))
        return self.assets[key]

    def view(self, token, state):
        if not self.authorized(token):
            raise PermissionError("Receiver session expired")
        status = self.snapshot()
        item = self.registered(token)
        if item:
            self.registry.heartbeat(token)
            status["device"] = item
            if item["id"] != self.active_id or not self.token:
                status.update(phase="idle", location="idle")
        if self.direct:
            self.direct.decorate(token, status)
        if token == self.preview_token:
            status.update(phase="preview", location="preview")
        from . import scene
        from .profiles import current_character

        from .scene_sets import environment

        place_id = (
            item["id"]
            if item
            else self.direct.source_id
            if self.direct and self.direct.role(token) == "source"
            else self.direct.target_id
            if self.direct and self.direct.role(token) == "target"
            else next(p["id"] for p in status["locations"] if p["adapter"] == "cast")
            if token == self.preview_token
            else self.active_id
        )
        place = next(p for p in status["locations"] if p["id"] == place_id)

        from .morning import Morning
        from .config import state_dir

        morning = Morning(state_dir() / "amadeus").view(place_id)
        return dict(
            status,
            morning=morning,
            environment=environment(
                place, current_character()["style"], self.registry.scene_world_enabled()
            ),
            character={
                k: v
                for k, v in current_character().items()
                if k in ("name", "style", "palette", "intensity")
            },
            profile=state.get("profile"),
            agenda=state.get("agenda", {}),
            focus=state.get("focus", {}),
            notification=state.get("active_notification"),
            deployments=state.get("deployments", []),
            device_health=state.get("device_health", {}),
            server_time=time.time(),
            presenter={
                k: v
                for k, v in scene.live().items()
                if k in ("activity", "emotion", "envelope", "start_at", "updated_at")
            },
        )

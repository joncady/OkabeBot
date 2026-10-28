"""Independent passive Cast connections for additional configured screen targets."""

import threading


class CastSurfaces:
    def __init__(self, settings, primary):
        self.settings, self.primary = settings, primary
        self.targets = {}
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.primary_id = next(p["id"] for p in settings["locations"] if p["adapter"] == "cast")
        for place in settings["locations"]:
            if place["adapter"] == "cast" and place.get("cast_host"):
                threading.Thread(target=self.connect, args=(dict(place),), daemon=True).start()

    def get(self, identity):
        place = next((p for p in self.settings["locations"] if p["id"] == identity), None)
        if not place or place["adapter"] != "cast":
            return None
        if identity == self.primary_id and not place.get("cast_host"):
            cast = self.primary()
        else:
            with self.lock:
                cast = self.targets.get(identity)
        if cast and cast.socket_client.is_alive() and cast.socket_client.is_connected:
            return cast
        return None

    def connect(self, place):
        import pychromecast

        while not self.stop.is_set():
            cast, browser = None, None
            try:
                casts, browser = pychromecast.get_chromecasts(
                    timeout=4, known_hosts=[place["cast_host"]]
                )
                cast = next((c for c in casts if c.cast_info.host == place["cast_host"]), None)
                # Discovery can return other devices. Never target a nearby TV
                # merely because it was first, or shares a friendly name.
                for other in casts:
                    if other is not cast:
                        try:
                            other.disconnect()
                        except RuntimeError:
                            pass
                if cast is None:
                    raise RuntimeError("Configured receiver not found")
                cast.wait(timeout=8)
                with self.lock:
                    self.targets[place["id"]] = cast
                while not self.stop.wait(2):
                    if not cast.socket_client.is_alive() or not cast.socket_client.is_connected:
                        break
            except Exception:
                pass
            finally:
                with self.lock:
                    self.targets.pop(place["id"], None)
                if cast:
                    try:
                        cast.disconnect()
                    except RuntimeError:
                        pass
                if browser:
                    browser.stop_discovery()
            self.stop.wait(5)

    def close(self):
        self.stop.set()

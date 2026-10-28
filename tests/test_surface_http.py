"""Real loopback HTTP boundary tests with fake hardware and no model workers."""

import json
import threading
import tempfile
from pathlib import Path
import unittest
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from okabebot.bridge import handler
from okabebot.surfaces import Surfaces


class SurfaceHttpTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        registry = patch(
            "okabebot.surface_registry.registry_path",
            return_value=Path(folder.name) / "registry.json",
        )
        registry.start()
        self.addCleanup(registry.stop)
        self.surface = Surfaces(Mock(return_value={"frames": [[]] * 6}), start=False)
        self.surface.preview("http://unused")
        from okabebot.surface_audio import AudioHub

        self.controller = SimpleNamespace(
            surface_audio=AudioHub(),
            surfaces=self.surface,
            token="full-controller-secret",
            snapshot=lambda: {
                "messages": ["private transcript"],
                "approvals": ["private"],
                "notifications": ["private"],
                "device_health": {},
            },
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.controller))
        self.base = "http://127.0.0.1:%s" % self.server.server_port
        self.controller.allowed_hosts = {self.base.split("//")[1]}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, token="", data=None, host=None):
        headers = {"X-Surface-Token": token, "Content-Type": "application/json"}
        if host:
            headers["Host"] = host
        return urlopen(
            Request(
                self.base + path,
                headers=headers,
                data=None if data is None else json.dumps(data).encode(),
            ),
            timeout=2,
        )

    def test_preview_is_read_only_and_never_receives_transcripts(self):
        with self.request("/surfaces/state", self.surface.preview_token) as r:
            value = json.load(r)
        self.assertEqual(value["phase"], "preview")
        self.assertFalse({"messages", "approvals", "notifications"} & set(value))
        for path in ("/surfaces/heartbeat", "/surfaces/ack", "/surfaces/return-receiver"):
            with self.assertRaises(HTTPError) as e:
                self.request(path, self.surface.preview_token, {})
            self.assertEqual(e.exception.code, 403)
        self.surface.rpc.assert_not_called()

    def test_full_control_token_does_not_substitute_for_a_receiver_token(self):
        with self.assertRaises(HTTPError) as e:
            self.request("/surfaces/state", self.controller.token)
        self.assertEqual(e.exception.code, 403)
        with self.assertRaises(HTTPError) as e:
            self.request("/surfaces/state", self.surface.preview_token, host="untrusted.example")
        self.assertEqual(e.exception.code, 403)

    def test_live_receiver_ack_must_match_transition(self):
        self.surface.begin("http://unused", launch=False)
        with self.request("/surfaces/heartbeat", self.surface.token, {}) as r:
            self.assertTrue(json.load(r)["receiver_connected"])
        with self.assertRaises(HTTPError) as e:
            self.request(
                "/surfaces/ack", self.surface.token, {"kind": "entered", "transition_id": "old"}
            )
        self.assertEqual(e.exception.code, 400)
        self.assertEqual(self.surface.phase, "preparing")
        self.surface.rpc.assert_not_called()

    def test_room_asset_and_remote_input_use_the_actual_http_routes(self):
        with self.request("/lab-room.js") as response:
            self.assertIn(b"class Room", response.read())
        self.surface.begin("http://unused", launch=False)
        with self.request("/surfaces/input", self.surface.token, {"key": "Enter"}) as response:
            self.assertTrue(json.load(response)["accepted"])
        self.assertEqual(self.surface.remote_input["key"], "Enter")
        self.surface.rpc.assert_not_called()

    def test_receiver_close_is_scoped_and_leaves_a_pending_return(self):
        self.surface.begin("http://unused", launch=False)
        token = self.surface.token
        self.surface.phase = "tv"
        with self.request(
            "/surfaces/closed", token, {"transition_id": self.surface.identifier}
        ) as response:
            self.assertEqual(json.load(response)["phase"], "entering_pi")
        self.assertFalse(self.surface.authorized(token))
        self.surface.rpc.assert_not_called()
        with self.assertRaises(HTTPError) as error:
            self.request(
                "/surfaces/closed",
                self.surface.preview_token,
                {"transition_id": self.surface.identifier},
            )
        self.assertEqual(error.exception.code, 403)

    def test_discovered_device_is_pending_and_cannot_read_until_approved(self):
        secret = "a" * 64
        with self.request(
            "/surfaces/register", secret, {"name": "Phone", "kind": "browser"}
        ) as response:
            device = json.load(response)
        self.assertFalse(device["approved"])
        with self.assertRaises(HTTPError):
            self.request("/surfaces/state", secret)
        self.surface.layout({"id": device["id"], "approved": True})
        with self.request("/surfaces/state", secret) as response:
            state = json.load(response)
        self.assertEqual(state["phase"], "idle")
        self.assertNotIn("messages", state)
        with self.assertRaises(HTTPError):
            self.request(
                "/surfaces/voice", secret, {"clip_id": "screen-test1234", "wav_base64": ""}
            )
        with self.assertRaises(HTTPError):
            self.request(
                "/surfaces/register",
                secret,
                {"name": "Phone", "kind": "browser"},
                host="attacker.example",
            )

    def test_stable_native_url_serves_the_same_screen_page(self):
        with self.request("/companion/?native=1") as response:
            self.assertIn(b"Hold to talk", response.read())

    def test_audio_poll_is_paired_and_does_not_expose_other_devices(self):
        payload = {"session": "a" * 32, "after": 0, "enabled": True}
        with self.assertRaises(HTTPError):
            self.request("/surfaces/audio", "a" * 64, payload)
        with self.request(
            "/surfaces/register", "a" * 64, {"name": "Phone", "kind": "browser"}
        ) as response:
            device = json.load(response)
        self.surface.layout({"id": device["id"], "approved": True})
        with self.request("/surfaces/audio", "a" * 64, payload) as response:
            self.assertEqual(json.load(response)["events"], [])
        self.assertTrue(self.controller.surface_audio.ready(device["id"]))
        with self.assertRaises(HTTPError):
            self.request("/surfaces/audio", self.controller.token, payload)

    def test_full_control_audio_chunks_have_a_separate_bounded_body_limit(self):
        import base64
        from okabebot.application import Application

        self.controller.application = Application(self.controller)
        hub = self.controller.surface_audio
        hub.poll("phone", {"session": "a" * 32, "after": 0, "enabled": True})
        identifier = hub.command("phone", {"op": "stream_start"})["stream_id"]
        payload = {
            "device_id": "phone",
            "command": {
                "op": "stream_chunk",
                "stream_id": identifier,
                "sequence": 0,
                "pcm_base64": base64.b64encode(b"\0" * 48000).decode(),
            },
        }
        raw = json.dumps(payload).encode()
        self.assertGreater(len(raw), 20000)
        with urlopen(
            Request(
                self.base + "/audio/stream",
                data=raw,
                headers={
                    "X-Hardware-Token": self.controller.token,
                    "Content-Type": "application/json",
                },
            ),
            timeout=2,
        ) as response:
            self.assertIn("playback_started_at", json.load(response))
        self.assertEqual(hub.streams[identifier]["bytes"], 48000)

    def test_screen_can_summon_only_itself_after_approval(self):
        self.controller.port = self.server.server_port
        secret = "a" * 64
        with self.request(
            "/surfaces/register", secret, {"name": "Phone", "kind": "browser"}
        ) as response:
            device = json.load(response)
        with self.assertRaises(HTTPError):
            self.request("/surfaces/summon", secret, {})
        self.surface.layout({"id": device["id"], "approved": True})
        with self.request("/surfaces/summon", secret, {}) as response:
            state = json.load(response)
        self.assertTrue(state["accepted"])
        self.assertEqual(state["destination_location"], device["id"])
        self.assertNotIn("url", state)
        with self.assertRaises(HTTPError):
            self.request("/surfaces/summon", secret, {"location_id": "living-room"})
        with self.assertRaises(HTTPError):
            self.request("/surfaces/summon", self.surface.preview_token, {})
        self.surface.rpc.assert_not_called()

    def test_companion_setup_assets_are_public_without_controller_authority(self):
        for path, expected in (
            ("/companion/", b'aria-label="Companion setup"'),
            ("/companion-ui.js", b"class CompanionUI"),
            ("/character-environments.js", b"green-hill"),
            ("/surface-theme.css", b"--pixel-bg"),
        ):
            with self.request(path) as response:
                self.assertIn(expected, response.read())
        self.surface.rpc.assert_not_called()

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch
from PIL import Image
from okabebot.bridge import Bridge
from okabebot.adapters.media import MediaSnapshot
from pi import prop_art


class MediaRecoveryTests(unittest.TestCase):
    def test_unchanged_media_republished_and_restart_restores_character(self):
        bridge = Bridge.__new__(Bridge)
        iterations = 0

        class Closing:
            def is_set(self):
                return iterations >= 3

            def wait(self, duration):
                nonlocal iterations
                iterations += 1

        bridge.closing = Closing()
        bridge.media_source = SimpleNamespace(poll=lambda: {"is_playing": False}, tv={})
        bridge.media_source.read = lambda: MediaSnapshot(
            bridge.media_source.poll(), dict(bridge.media_source.tv)
        )
        bridge.team_resolver = SimpleNamespace(
            get=lambda tv: {}, results={"old": "asset"}, lock=threading.Lock()
        )
        bridge.content_preview = SimpleNamespace(music=lambda: None)
        bridge.sources = SimpleNamespace(state={}, errors={})
        with (
            patch("okabebot.bridge.time.monotonic", side_effect=lambda: iterations * 16),
            patch(
                "okabebot.bridge.scene.rpc",
                side_effect=[{"session_id": "one"}, {"session_id": "two"}, {"session_id": "two"}],
            ),
            patch("okabebot.bridge.scene.set_music") as media,
            patch("okabebot.bridge.scene.set_activity") as character,
            patch("okabebot.bridge.scene.set_deploying"),
        ):
            bridge.poll_music()
        self.assertEqual(media.call_count, 3)
        self.assertEqual(character.call_count, 2)
        self.assertEqual(bridge.team_resolver.results, {})

    def test_atlas_honors_manifest_filename_and_corrupt_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new("RGBA", (32, 16)).save(root / "alternate.png")
            manifest = {
                "image": "alternate.png",
                "order": ["cinema", "soccer"],
                "columns": 2,
                "rows": 1,
            }
            (root / "content-props.json").write_text(json.dumps(manifest))
            try:
                with patch.object(prop_art, "ROOT", root):
                    prop_art.atlas.cache_clear()
                    self.assertTrue(prop_art.available())
                    prop_art.atlas.cache_clear()
                    (root / "alternate.png").write_text("broken")
                    self.assertFalse(prop_art.available())
            finally:
                prop_art.atlas.cache_clear()

    def test_dead_tunnel_reconnects_on_next_request_without_replaying_action(self):
        from contextlib import contextmanager
        from okabebot.transport import PooledDevice

        endpoint = PooledDevice({"transport": "ssh"})
        calls = []
        sessions = []

        @contextmanager
        def connect(timeout):
            generation = len(sessions)
            sessions.append(generation)

            def call(data):
                calls.append((generation, data["op"]))
                if generation == 0:
                    raise OSError("connection lost after action")
                return {"ok": True}

            yield call

        with patch.object(endpoint, "connect", side_effect=connect):
            with self.assertRaises(OSError):
                endpoint.rpc({"op": "press"})
            self.assertEqual(endpoint.rpc({"op": "status"}), {"ok": True})
            endpoint.close()
        self.assertEqual(calls, [(0, "press"), (1, "status")])

    def test_titleless_prime_shows_app_without_inventing_identity_or_progress(self):
        bridge = Bridge.__new__(Bridge)
        done = False

        class Closing:
            def is_set(self):
                return done

            def wait(self, duration):
                nonlocal done
                done = True

        bridge.closing = Closing()
        bridge.media_source = SimpleNamespace(
            poll=lambda: {"is_playing": False},
            tv={
                "app": "Prime Video",
                "title": None,
                "state": "PLAYING",
                "position": 0,
                "duration": 6000,
            },
        )
        bridge.media_source.read = lambda: MediaSnapshot(
            bridge.media_source.poll(), dict(bridge.media_source.tv)
        )
        bridge.team_resolver = SimpleNamespace(get=lambda tv: {}, results={}, lock=threading.Lock())
        bridge.content_preview = SimpleNamespace(music=lambda: None)
        bridge.content_context = SimpleNamespace(get=lambda tv, fallback: {})
        bridge.sources = SimpleNamespace(state={}, errors={})
        with (
            patch("okabebot.bridge.scene.rpc", return_value={"session_id": "one"}),
            patch("okabebot.bridge.scene.set_activity"),
            patch("okabebot.bridge.scene.set_deploying"),
            patch("okabebot.bridge.scene.set_music") as publish,
        ):
            bridge.poll_music()
        video = publish.call_args.args[0]["video"]
        self.assertEqual(video["title"], "Title unavailable")
        self.assertIsNone(video["position"])
        self.assertIsNone(bridge.media_source.tv["title"])

    def test_media_brands_are_distinct_and_unknown_apps_keep_tv_fallback(self):
        from pi import scene

        names = [
            "Prime Video",
            "HBO Max",
            "fuboTV Live Production",
            "Spotify",
            "YouTube",
            "Netflix",
        ]
        icons = [scene.icon(scene.media_source(name)).tobytes() for name in names]
        self.assertEqual(len(set(icons)), len(names))
        self.assertEqual(scene.media_source("Unknown app"), "tv")
        preview = scene.music_card({"is_playing": True, "title": "Song", "artist": "Artist"})
        self.assertGreater(preview.crop((16, 280, 48, 312)).getbbox()[2], 0)

    def test_recovered_display_clears_old_deployment_error(self):
        bridge = Bridge.__new__(Bridge)
        finished = False

        class Closing:
            def is_set(self):
                return finished

            def wait(self, seconds):
                nonlocal finished
                finished = True

        bridge.closing = Closing()
        bridge.sources = SimpleNamespace(
            poll=lambda: None, state={}, errors={"display": "Deployment indicator unavailable"}
        )
        with patch("okabebot.bridge.scene.set_deploying"):
            bridge.poll_sources()
        self.assertNotIn("display", bridge.sources.errors)

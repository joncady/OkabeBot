import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from okabebot.spotify import Spotify, playback
from pi import scene


class SpotifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.spotify = Spotify(
            self.tmp.name, dict(callback_port=8769, poll_seconds=15, device_name="")
        )

    def test_control_is_opt_in_and_permission_checked(self):
        with self.assertRaises(ValueError):
            self.spotify.control("next")
        self.spotify.settings["playback_control"] = True
        self.spotify.tokens = dict(client_id="client", scope="user-read-playback-state")
        with patch("okabebot.spotify.env_value", return_value="client"):
            with self.assertRaisesRegex(ValueError, "grant playback control"):
                self.spotify.control("next")

    def test_control_sends_exact_uri_without_polling(self):
        from unittest.mock import MagicMock

        self.spotify.settings["playback_control"] = True
        self.spotify.tokens = dict(
            client_id="client",
            scope="user-modify-playback-state",
            access_token="test",
            expires_at=time.time() + 3600,
        )
        with (
            patch("okabebot.spotify.env_value", return_value="client"),
            patch("okabebot.spotify.urlopen", return_value=MagicMock()) as send,
        ):
            result = self.spotify.control("play", "spotify:track:" + "a" * 22)
            request = send.call_args.args[0]
            self.assertEqual(request.method, "PUT")
            self.assertEqual(json.loads(request.data), {"uris": ["spotify:track:" + "a" * 22]})
            self.assertTrue(result["accepted"])
            send.assert_called_once()
            with self.assertRaises(ValueError):
                self.spotify.control("play", "https://untrusted.example/song")
            send.assert_called_once()

    def test_pkce_single_use_and_tokens_private(self):
        with (
            patch("okabebot.spotify.env_value", return_value="client"),
            patch("okabebot.spotify.ThreadingHTTPServer"),
            patch("okabebot.spotify.threading.Thread"),
        ):
            query = parse_qs(urlsplit(self.spotify.begin()).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["scope"], ["user-read-playback-state"])
        with self.assertRaises(ValueError):
            self.spotify.complete(dict(state=["wrong"], code=["code"]))
        self.assertIsNotNone(self.spotify.pending)
        with patch.object(
            self.spotify,
            "exchange",
            return_value=dict(access_token="private", refresh_token="refresh"),
        ) as exchange:
            self.spotify.complete(dict(state=query["state"], code=["code"]))
        self.assertIn("code_verifier", exchange.call_args.args[0])
        self.assertEqual(self.spotify.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            self.spotify.complete(dict(state=query["state"], code=["code"]))
        with patch("okabebot.spotify.env_value", return_value="client"):
            self.assertNotIn("private", json.dumps(self.spotify.status()))
            self.assertTrue(self.spotify.status()["connected"])

    def test_playback_privacy_pause_device_filter(self):
        data = dict(
            is_playing=True,
            device=dict(name="Office"),
            item=dict(name="Song", artists=[dict(name="Artist")]),
        )
        self.assertTrue(playback(data)["is_playing"])
        self.assertFalse(playback(data, "Bedroom")["is_playing"])
        data["device"]["is_private_session"] = True
        self.assertEqual(playback(data)["title"], "")
        self.assertFalse(playback({})["is_playing"])

    def test_expired_authorization_and_corrupt_token_file(self):
        self.spotify.pending = dict(state="state", expires=time.time() - 1)
        with self.assertRaises(ValueError):
            self.spotify.complete(dict(state=["state"]))
        Path(self.tmp.name, "spotify-tokens.json").write_text("[]")
        other = Spotify(self.tmp.name, self.spotify.settings)
        self.assertEqual(other.tokens, {})

    def test_notification_overrides_music(self):
        notification = dict(source="github", title="Build finished", body="Ready")
        music = dict(is_playing=True, title="Song", artist="Artist")
        self.assertEqual(
            scene.render(notification=notification).tobytes(),
            scene.render(notification=notification, music=music).tobytes(),
        )

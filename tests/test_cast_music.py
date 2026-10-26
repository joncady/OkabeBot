import unittest
from types import SimpleNamespace
from okabebot.cast_music import CastMusic


class CastMusicTests(unittest.TestCase):
    def setUp(self):
        self.source = CastMusic.__new__(CastMusic)
        self.source.settings = {"device_name": "TV"}
        self.source.music = {}
        self.source.app = "Spotify"
        self.source.tv = {}

    def test_callbacks_clear_stale_playback(self):
        s = SimpleNamespace(
            content_type="application/x-spotify.track",
            player_state="PLAYING",
            title="Track",
            artist="Artist",
        )
        self.source.new_media_status(s)
        self.assertTrue(self.source.poll()["is_playing"])
        s.player_state = "PAUSED"
        self.source.new_media_status(s)
        self.assertFalse(self.source.poll()["is_playing"])
        s.player_state = "PLAYING"
        self.source.new_media_status(s)
        self.source.new_connection_status(SimpleNamespace(status="DISCONNECTED"))
        self.assertEqual(self.source.poll(), {"is_playing": False})
        self.source.new_media_status(s)
        self.source.new_cast_status(SimpleNamespace(display_name="Netflix"))
        self.assertEqual(self.source.poll(), {"is_playing": False})
        self.assertEqual(self.source.tv, {})
        s.content_type = "video/mp4"
        self.source.new_media_status(s)
        self.assertEqual(self.source.poll(), {"is_playing": False})

    def test_youtube_context_does_not_start_music_meter(self):
        self.source.new_cast_status(SimpleNamespace(display_name="YouTube"))
        self.source.new_media_status(
            SimpleNamespace(
                title="Video",
                player_state="PLAYING",
                content_type="x-youtube/video",
                current_time=42,
                duration=100,
                content_id="video-id",
            )
        )
        self.assertEqual(self.source.tv["app"], "YouTube")
        self.assertEqual(self.source.tv["position"], 42)
        self.assertEqual(self.source.poll(), {"is_playing": False})

    def test_fubo_receiver_title_survives_failed_load(self):
        self.source.new_cast_status(
            SimpleNamespace(
                display_name="fuboTV Live Production",
                status_text="Casting: FC Barcelona vs Real Madrid",
                icon_url=None,
            )
        )
        self.assertEqual(self.source.tv["title"], "FC Barcelona vs Real Madrid")
        self.source.new_media_status(
            SimpleNamespace(title=None, player_state="UNKNOWN", content_type=None)
        )
        self.assertEqual(self.source.tv["title"], "FC Barcelona vs Real Madrid")
        self.assertEqual(self.source.tv["state"], "BUFFERING")
        self.source.new_cast_status(
            SimpleNamespace(display_name="YouTube", status_text="", icon_url=None)
        )
        self.assertEqual(self.source.tv, {})

    def test_fubo_uses_stable_id_without_playback_credentials(self):
        self.source.app = "fuboTV"
        self.source.receiver_title = "Team A vs Team B"
        status = SimpleNamespace(
            title="Team A vs Team B",
            player_state="BUFFERING",
            content_type="application/x-mpegurl",
            content_id="https://example.com/video?token=secret",
        )
        self.source.new_media_status(status)
        first = self.source.tv["content_id"]
        status.content_id = "https://example.com/video?token=rotated"
        self.source.new_media_status(status)
        self.assertEqual(first, self.source.tv["content_id"])
        self.assertNotIn("secret", str(self.source.tv))

    def test_media_before_receiver_keeps_new_youtube_video(self):
        self.source.new_media_status(
            SimpleNamespace(
                title="New video",
                player_state="PLAYING",
                content_type="x-youtube/video",
                content_id="new",
            )
        )
        self.source.new_cast_status(SimpleNamespace(display_name="YouTube"))
        self.assertEqual(self.source.tv["title"], "New video")
        self.assertEqual(self.source.tv["app"], "YouTube")
        self.source.new_connection_status(SimpleNamespace(status="DISCONNECTED"))
        self.source.new_cast_status(SimpleNamespace(display_name="YouTube"))
        self.assertEqual(self.source.tv, {})

    def test_fubo_cancellation_does_not_imply_buffering(self):
        self.source.new_cast_status(
            SimpleNamespace(display_name="fuboTV", status_text="Casting: A vs B")
        )
        self.source.new_media_status(
            SimpleNamespace(
                title=None, player_state="IDLE", idle_reason="CANCELLED", content_type=None
            )
        )
        self.assertEqual(self.source.tv["state"], "IDLE")

    def test_app_transition_never_launches_or_refreshes_receiver(self):
        from unittest.mock import Mock

        self.source.cast = SimpleNamespace(media_controller=SimpleNamespace(update_status=Mock()))
        self.source.new_cast_status(SimpleNamespace(display_name="Prime Video"))
        self.source.cast.media_controller.update_status.assert_not_called()
        self.source.new_media_status(
            SimpleNamespace(
                title=None, player_state="PLAYING", content_type="video/mp4", duration=6000
            )
        )
        self.assertEqual(self.source.tv["app"], "Prime Video")
        self.assertFalse(self.source.tv["title"])
        self.assertEqual(self.source.tv["state"], "PLAYING")
        self.source.new_cast_status(SimpleNamespace(display_name="Prime Video"))
        self.source.cast.media_controller.update_status.assert_not_called()

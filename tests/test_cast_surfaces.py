"""No network or receiver control: discovery and selection contracts."""

import copy
import unittest
from unittest.mock import Mock, patch
from okabebot.cast_surfaces import CastSurfaces
from okabebot.config import DEFAULTS, load
from okabebot.surfaces import Surfaces
from tests.test_locations import CUSTOM
import json
import tempfile
from pathlib import Path


class CastSurfaceTests(unittest.TestCase):
    def settings(self):
        config = copy.deepcopy(DEFAULTS)
        config["surfaces"]["locations"] = copy.deepcopy(CUSTOM) + [
            dict(
                id="upstairs",
                name="Upstairs TV",
                aliases=["upstairs"],
                adapter="cast",
                cast_host="192.168.1.22",
            )
        ]
        return config

    def test_each_destination_has_independent_connection(self):
        settings = self.settings()["surfaces"]
        primary, second = Mock(), Mock()
        with patch("okabebot.cast_surfaces.threading.Thread"):
            pool = CastSurfaces(settings, lambda: primary)
        pool.targets["upstairs"] = second
        self.assertIs(pool.get("den-screen"), primary)
        self.assertIs(pool.get("upstairs"), second)
        self.assertIsNone(pool.get("desk-nook"))
        pool.targets.clear()
        self.assertIs(pool.get("den-screen"), primary)
        self.assertIsNone(pool.get("upstairs"))

    def test_discovery_uses_exact_host_not_friendly_name_or_first_result(self):
        settings = self.settings()["surfaces"]
        with patch("okabebot.cast_surfaces.threading.Thread"):
            pool = CastSurfaces(settings, lambda: None)
        wrong, correct, browser = Mock(), Mock(), Mock()
        wrong.cast_info.host = "192.168.1.99"
        wrong.disconnect.side_effect = RuntimeError("unstarted thread")
        correct.cast_info.host = "192.168.1.22"
        correct.socket_client.is_alive.side_effect = lambda: pool.stop.set() or False
        with patch(
            "pychromecast.get_chromecasts", return_value=([wrong, correct], browser)
        ) as discover:
            pool.connect(settings["locations"][-1])
        discover.assert_called_once_with(timeout=4, known_hosts=["192.168.1.22"])
        correct.wait.assert_called_once_with(timeout=8)
        wrong.wait.assert_not_called()
        correct.disconnect.assert_called_once()
        browser.stop_discovery.assert_called_once()
        self.assertEqual(pool.targets, {})

    def test_additional_tv_does_not_fall_back_to_primary(self):
        config = self.settings()
        primary = Mock()
        with patch("okabebot.config.get_config", return_value=config):
            s = Surfaces(Mock(), cast_getter=lambda: primary, start=False)
        self.assertIs(s.cast_for("den-screen"), primary)
        self.assertIsNone(s.cast_for("upstairs"))

    def test_additional_tv_launch_captures_destination(self):
        config = self.settings()
        with patch("okabebot.config.get_config", return_value=config):
            s = Surfaces(Mock(), start=False)
            with patch("okabebot.surfaces.threading.Thread") as thread:
                s.begin("http://test", location_id="upstairs")
            self.assertEqual(thread.call_args.kwargs["args"][2], "upstairs")
            self.assertEqual(s.active_id, "upstairs")

    def test_invalid_or_duplicate_receivers_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for host in [None, "127.0.0.1", "8.8.8.8", "192.168.1.23"]:
                config = self.settings()
                config["spotify"]["cast_host"] = "192.168.1.23"
                if host is None:
                    config["surfaces"]["locations"][-1].pop("cast_host")
                else:
                    config["surfaces"]["locations"][-1]["cast_host"] = host
                path.write_text(json.dumps(config))
                with self.subTest(host=host), self.assertRaises(ValueError):
                    load(path)

    def test_cec_standby_without_confirmed_active_input_does_not_end_visit(self):
        from pychromecast.config import APP_DASHCAST

        config = self.settings()
        cast = Mock()
        cast.status.app_id = APP_DASHCAST
        cast.status.session_id = "owned"
        cast.status.is_stand_by = True
        cast.status.is_active_input = None
        with patch("okabebot.config.get_config", return_value=config):
            s = Surfaces(Mock(), cast_resolver=lambda identity: cast, start=False)
        self.assertFalse(s._location_gone("upstairs", "owned", False))
        self.assertTrue(s._location_gone("upstairs", "owned", True))
        cast.status.app_id = "a-new-user-app"
        self.assertTrue(s._location_gone("upstairs", "owned", False))

    def test_reconnecting_socket_is_not_available_for_a_handoff(self):
        settings = self.settings()["surfaces"]
        with patch("okabebot.cast_surfaces.threading.Thread"):
            pool = CastSurfaces(settings, lambda: None)
        cast = Mock()
        cast.socket_client.is_alive.return_value = True
        cast.socket_client.is_connected = False
        pool.targets["upstairs"] = cast
        self.assertIsNone(pool.get("upstairs"))
        cast.socket_client.is_connected = True
        self.assertIs(pool.get("upstairs"), cast)
        cast.socket_client.is_alive.return_value = False
        self.assertIsNone(pool.get("upstairs"))

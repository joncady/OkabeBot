"""Real location registry/handoff with fake Pi and private store; no hardware."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from okabebot.config import DEFAULTS
from okabebot.surface_registry import Registry
from okabebot.surfaces import Surfaces
from okabebot.alexa_destination_bridge import ControllerDestination, SurfaceClient
from tests.test_alexa_destination_relay import Store


class BridgeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "screens.json"
        config = copy.deepcopy(DEFAULTS)
        for p in [
            patch("okabebot.surface_registry.registry_path", return_value=path),
            patch("okabebot.config.get_config", return_value=config),
            patch(
                "okabebot.profiles.current_character",
                return_value={"style": "okabe", "name": "Okabe"},
            ),
            patch("okabebot.scene.live", return_value={}),
        ]:
            p.start()
            self.addCleanup(p.stop)
        self.drawn = "home"
        self.calls = []
        self.surface = Surfaces(self.rpc, start=False)
        self.surface.registry.initialize_scenes(config["surfaces"]["locations"])
        self.store = Store()
        self.now = 1000
        self.record = dict(
            token="1" * 64,
            device="2" * 64,
            started_at=1000,
            expires_at=1060,
            updated_at=1000,
            clock=1000,
            ready=True,
            painted="hidden",
            transition="",
            closed=False,
            character="okabe",
            set="maid-cafe",
        )
        self.store.put("session", self.record)
        self.worker = ControllerDestination(
            self.store, self.api, "Study Echo", clock=lambda: self.now
        )

    def rpc(self, data):
        if data["op"] == "presence":
            self.drawn = "home" if data["phase"] == "arriving" else "away"
        return {"presence": {"transition_id": self.surface.identifier, "rendered": self.drawn}}

    def api(self, path, data, token):
        self.calls.append((path, copy.deepcopy(data)))
        if path == "/surfaces/register":
            return self.surface.registry.register(
                token, data["name"], data["kind"], data["supported_scenes"]
            )
        if path == "/surfaces/state":
            return self.surface.view(token, {})
        if path == "/surfaces/summon":
            return self.surface.move(Registry.identity(token), "http://controller")
        if path == "/surfaces/heartbeat":
            return self.surface.heartbeat(token)
        if path == "/surfaces/ack":
            return self.surface.acknowledge(token, data["kind"], data["transition_id"])
        raise AssertionError("Unexpected authority: " + path)

    def poll(self, painted="hidden", transition=""):
        self.record.update(
            clock=self.record["clock"] + 1000,
            updated_at=self.now,
            painted=painted,
            transition=transition,
        )
        self.store.put("session", self.record)
        return self.worker.step()

    def approve(self):
        self.assertEqual(self.worker.step(), "approval_required")
        self.identity = Registry.identity(self.record["device"])
        self.surface.layout({"id": self.identity, "approved": True})
        self.surface.layout({"id": self.identity, "scene_selections": {"okabe": "maid-cafe"}})

    def test_full_arrival_return_uses_existing_ownership_and_no_dashboard_authority(self):
        self.approve()
        self.assertEqual(self.worker.step(), "connected")
        self.assertEqual(self.store.get("command")["phase"], "hidden")
        self.assertEqual(self.surface.phase, "pi")
        self.surface.move(self.identity, "http://controller")
        self.poll()
        self.surface.tick()
        self.assertEqual(self.surface.phase, "leaving_pi")
        self.surface.tick()
        self.assertEqual(self.surface.phase, "entering_tv")
        self.poll()
        command = self.store.get("command")
        self.assertEqual(command["phase"], "entering")
        self.assertEqual(self.drawn, "away")
        self.poll("entered", command["generation"])
        self.assertEqual(self.surface.phase, "tv")
        self.assertEqual(self.store.get("command")["phase"], "present")
        self.surface.return_home()
        self.poll()
        command = self.store.get("command")
        self.assertEqual(command["phase"], "leaving")
        self.poll("departed", command["generation"])
        self.assertEqual(self.surface.phase, "entering_pi")
        self.surface.tick()
        self.surface.tick()
        self.assertEqual(self.surface.phase, "pi")
        self.assertEqual(self.drawn, "home")
        self.assertFalse(
            any(
                path in ("/surfaces/move", "/surfaces/layout", "/character")
                for path, _ in self.calls
            )
        )
        self.assertNotIn("Study Echo", str(self.store.get("command")))

    def test_unapproved_screen_does_not_move_or_receive_commands(self):
        self.assertEqual(self.worker.step(), "approval_required")
        self.assertEqual(self.surface.phase, "pi")
        self.assertIsNone(self.store.get("command"))
        self.assertEqual([path for path, _ in self.calls], ["/surfaces/register"])

    def test_registry_rejects_unsupported_artwork_and_mutating_capabilities(self):
        self.approve()
        for values in [
            {"scene_selections": {"okabe": "pixel-lab"}},
            {"scene_selections": {"kurisu": "maid-cafe"}},
            {"presentation": "companion"},
        ]:
            with self.assertRaises(ValueError):
                self.surface.layout(dict(id=self.identity, **values))
        with self.assertRaises(ValueError):
            self.surface.registry.register(
                self.record["device"], "Study Echo", "alexa", {"okabe": ["pixel-lab"]}
            )
        with self.assertRaises(ValueError):
            self.surface.ensure_scene(self.identity, "kurisu")

    def test_restart_preserves_sequence_and_stale_or_closed_records_stop_heartbeats(self):
        self.approve()
        self.worker.step()
        old = self.store.get("command")["sequence"]
        worker = ControllerDestination(self.store, self.api, "Study Echo", clock=lambda: self.now)
        worker.step()
        self.assertGreater(self.store.get("command")["sequence"], old)
        count = len(self.calls)
        self.now += 4
        self.assertEqual(self.worker.step(), "inactive")
        self.assertEqual(len(self.calls), count)
        self.now -= 4
        self.record["closed"] = True
        self.store.put("session", self.record)
        self.assertEqual(self.worker.step(), "inactive")
        self.assertEqual(len(self.calls), count)

    def test_controller_urls_do_not_accept_embedded_dashboard_keys(self):
        for url in [
            "file:///tmp/x",
            "http://user:password@host/",
            "http://host/#secret",
            "http://host/?token=secret",
            "http://host/other",
        ]:
            with self.assertRaises(ValueError):
                SurfaceClient(url)
        self.assertEqual(SurfaceClient("http://127.0.0.1:8768/").base, "http://127.0.0.1:8768")

    def test_invalid_receiver_state_cannot_refresh_approved_screen_or_ack(self):
        self.approve()
        count = len(self.calls)
        for changes in [
            {"clock": True},
            {"clock": float("nan")},
            {"ready": "yes"},
            {"painted": "move"},
            {"transition": "bad"},
        ]:
            record = copy.deepcopy(self.record)
            record.update(changes)
            self.store.put("session", record)
            with self.assertRaises(ValueError):
                self.worker.step()
        self.assertEqual(len(self.calls), count)

    def test_explicit_visit_summons_once_and_restart_does_not_pull_character_back(self):
        self.approve()
        self.record["summon"] = True
        self.store.put("session", self.record)
        self.worker.step()
        self.assertEqual(self.surface.phase, "preparing")
        self.assertEqual(sum(path == "/surfaces/summon" for path, _ in self.calls), 1)
        self.surface.return_home()
        restarted = ControllerDestination(
            self.store, self.api, "Study Echo", clock=lambda: self.now
        )
        restarted.step()
        self.assertEqual(self.surface.phase, "pi")
        self.assertEqual(sum(path == "/surfaces/summon" for path, _ in self.calls), 1)

    def test_uncertain_summon_is_not_automatically_replayed(self):
        self.approve()
        self.record["summon"] = True
        self.store.put("session", self.record)
        original = self.worker.api
        attempted = []

        def api(path, data, token):
            if path == "/surfaces/summon":
                attempted.append(path)
                raise TimeoutError("uncertain result")
            return original(path, data, token)

        self.worker.api = api
        with self.assertRaises(TimeoutError):
            self.worker.step()
        self.worker.step()
        self.assertEqual(attempted, ["/surfaces/summon"])
        self.assertEqual(self.surface.phase, "pi")

    def test_new_poll_during_controller_read_renews_instead_of_starving(self):
        self.approve()
        self.worker.step()
        original = self.worker.api

        def advance_during_read(path, data, token):
            result = original(path, data, token)
            if path == "/surfaces/state":
                latest = self.store.get("session")
                latest["clock"] += 500
                self.store.put("session", latest)
            return result

        self.worker.api = advance_during_read
        previous = self.store.get("command")["sequence"]
        for _ in range(4):
            self.record["clock"] = self.store.get("session")["clock"] + 500
            self.store.put("session", self.record)
            self.assertEqual(self.worker.step(), "connected")
            command = self.store.get("command")
            self.assertGreater(command["sequence"], previous)
            self.assertEqual(command["receiver_elapsed_ms"], self.store.get("session")["clock"])
            previous = command["sequence"]
        self.assertEqual(self.surface.phase, "pi")
        self.assertEqual(self.drawn, "home")

    def test_close_during_controller_read_cannot_trigger_a_summon_or_ack(self):
        self.approve()
        self.record["summon"] = True
        self.store.put("session", self.record)
        original = self.worker.api

        def api(path, data, token):
            result = original(path, data, token)
            if path == "/surfaces/state":
                closed = self.store.get("session")
                closed["closed"] = True
                self.store.put("session", closed)
            return result

        self.worker.api = api
        self.assertEqual(self.worker.step(), "waiting_for_poll")
        self.assertEqual(self.surface.phase, "pi")
        self.assertFalse(
            any(
                path in ("/surfaces/summon", "/surfaces/heartbeat", "/surfaces/ack")
                for path, _ in self.calls
            )
        )

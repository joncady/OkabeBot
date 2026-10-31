"""Actual owner HTTP boundary against synthetic private storage, no device calls."""

import json
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from okabebot.amadeus import Store
from okabebot.amadeus_onboarding import SYSTEM, KEY
from okabebot.application import Application
from okabebot.bridge import handler
from okabebot.preparations import Preparations


class PreparationHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        with closing(Store(temp.name)) as store:
            store.remember(SYSTEM, KEY, dict(profile="invented", paused=False, guest=False))
        self.bridge = SimpleNamespace(
            token="invented-owner",
            notification_token="invented-publisher",
            surfaces=Mock(),
            preparations=Preparations(temp.name),
            sync_preparations=Mock(),
        )
        app = Application.__new__(Application)
        app.controller = self.bridge
        self.bridge.application = app
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.bridge))
        self.base = "http://127.0.0.1:%s" % self.server.server_port
        self.bridge.allowed_hosts = {self.base.split("//")[1]}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, data=None, token="invented-owner"):
        with urlopen(
            Request(
                self.base + path,
                data=None if data is None else json.dumps(data).encode(),
                headers={"X-Hardware-Token": token, "Content-Type": "application/json"},
            ),
            timeout=3,
        ) as response:
            return json.load(response)

    def test_reads_are_owner_only_and_do_not_start_work(self):
        self.assertEqual(self.request("/preparations")["jobs"], [])
        self.assertTrue(self.request("/presentation/motion")["enabled"])
        self.bridge.sync_preparations.assert_not_called()
        for path in ("/preparations", "/presentation/motion"):
            with self.assertRaises(HTTPError) as error:
                self.request(path, token="invented-publisher")
            self.assertEqual(error.exception.code, 403)

    def test_draft_route_does_not_accept_execution_or_arbitrary_work(self):
        self.request("/preparations/update", {"action": "draft_list", "items": ["Tea"]})
        self.assertEqual(self.request("/preparations")["jobs"][0]["status"], "awaiting_review")
        for data in (
            {"action": "order"},
            {"action": "draft_list", "items": []},
            {"action": "progress", "stage": "drafting"},
        ):
            with self.assertRaises(HTTPError):
                self.request("/preparations/update", data)
        self.assertEqual(len(self.request("/preparations")["jobs"]), 1)

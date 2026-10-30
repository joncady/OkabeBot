"""Invented tag IDs and destinations; no real scans or physical actions."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from okabebot.tags import Tags
from okabebot.tags_http import handle


class TagsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1000
        self.locations = [{"id": "desk", "name": "Example desk", "approved": True}]
        self.call = Mock(return_value={"accepted": True})
        self.tags = Tags(
            Path(self.tmp.name), lambda: self.locations, self.call, clock=lambda: self.now
        )
        self.mapping = {
            "tag_id": "invented-tag",
            "name": "Example",
            "location_id": "desk",
            "enabled": True,
        }
        self.event = {
            "tag_id": "invented-tag",
            "event_id": "invented-event",
            "observed_at": self.now,
        }

    def test_learn_never_executes_even_for_an_existing_mapping(self):
        self.tags.save(self.mapping)
        self.tags.learn()
        self.assertEqual(self.tags.scan(self.event)["status"], "registered_for_review")
        self.assertEqual(self.tags.snapshot()["learned"], "invented-tag")
        self.call.assert_not_called()
        self.now += 91
        self.assertIsNone(self.tags.snapshot()["learned"])

    def test_scan_revalidates_approval_and_survives_duplicate_after_restart(self):
        self.tags.save(self.mapping)
        self.assertEqual(self.tags.scan(self.event)["status"], "request_sent")
        other = Tags(Path(self.tmp.name), lambda: self.locations, self.call, clock=lambda: self.now)
        self.assertEqual(other.scan(self.event)["status"], "duplicate")
        self.call.assert_called_once_with("desk")
        self.now += 4
        self.locations[0]["approved"] = False
        result = self.tags.scan(dict(self.event, event_id="next-event", observed_at=self.now))
        self.assertEqual(result["status"], "destination_unavailable")
        self.assertEqual(self.call.call_count, 1)

    def test_invalid_disabled_unmapped_and_stale_never_execute(self):
        for event in [
            dict(self.event, observed_at=1),
            dict(self.event, observed_at=1001),
            dict(self.event, action="shell"),
        ]:
            with self.assertRaises(ValueError):
                self.tags.scan(event)
        self.assertEqual(self.tags.scan(self.event)["status"], "unmapped_or_disabled")
        self.tags.save(dict(self.mapping, enabled=False))
        self.now += 4
        self.assertEqual(
            self.tags.scan(dict(self.event, event_id="next", observed_at=self.now))["status"],
            "unmapped_or_disabled",
        )
        with self.assertRaises(ValueError):
            self.tags.save(dict(self.mapping, location_id="unknown"))
        self.call.assert_not_called()

    def test_failure_consumed_and_remove_does_not_move(self):
        self.tags.save(self.mapping)
        self.call.side_effect = RuntimeError("private detail")
        self.assertIn("failed", self.tags.scan(self.event)["status"])
        self.assertEqual(self.tags.scan(self.event)["status"], "duplicate")
        self.tags.remove("invented-tag")
        self.assertEqual(self.tags.snapshot()["mappings"], [])
        self.call.assert_called_once()

    def test_source_is_publish_only_and_requires_scoped_credential(self):
        bridge = SimpleNamespace(
            tags=self.tags, tag_source_token="x" * 40, allowed_hosts={"localhost:8768"}
        )

        def request(path, token, owner=False):
            raw = json.dumps(self.event).encode()
            handler = SimpleNamespace(
                path=path,
                headers={
                    "Host": "localhost:8768",
                    "Content-Length": str(len(raw)),
                    "X-Tag-Token": token,
                },
                authorized=lambda: owner,
                rfile=io.BytesIO(raw),
                connection=Mock(),
                respond=Mock(),
            )
            self.assertTrue(handle(handler, bridge, post=True))
            return handler.respond.call_args.args[0]

        self.assertEqual(request("/tags/source", "wrong"), 403)
        self.assertEqual(request("/tags/source", "é"), 403)
        self.assertEqual(request("/tags/save", "x" * 40), 403)
        self.assertEqual(request("/tags/refresh-areas", "x" * 40), 403)
        self.assertEqual(request("/tags/source", "x" * 40), 200)
        self.call.assert_not_called()

"""Invented chores and accelerated time only; no household activity or scans."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from okabebot.chores import Chores
from okabebot.chores_http import handle
from okabebot.amadeus_onboarding import Onboarding
from okabebot.tags import Tags
from tests.test_amadeus_http import SETUP


class ChoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.now = 2_000_000_000
        self.owner = Onboarding(self.path)
        self.addCleanup(self.owner.close)
        self.owner.store.clock = lambda: self.now
        self.owner.save(SETUP)
        self.owner.control({"paused": False})
        self.chores = Chores(self.path, clock=lambda: self.now)
        self.cfg = {
            "title": "Water imaginary fern",
            "interval_days": 14,
            "repeat_days": 1,
            "enabled": True,
        }

    def test_completion_restarts_delay_and_survives_restart_replay(self):
        item = self.chores.save(self.cfg)["item"]
        self.assertIsNone(item["last_done_at"])
        self.now += 100
        done = self.chores.complete(item["id"], "synthetic-scan")["item"]
        self.assertEqual(self.now + 14 * 86400, done["due_at"])
        self.now += 10
        other = Chores(self.path, clock=lambda: self.now)
        replay = other.complete(item["id"], "synthetic-scan")["item"]
        self.assertEqual(done["due_at"], replay["due_at"])
        self.now = done["due_at"] + 1
        self.assertEqual(item["id"], other.due()[0]["id"])
        self.assertTrue(other.claim_reminder(item["id"], "voice-one", "proactive"))
        self.assertEqual([], other.due(remind_only=True))
        self.assertEqual(1, len(other.due()))  # Reminder does not complete the chore.
        self.now += 86401
        self.assertEqual(1, len(other.due(remind_only=True)))
        self.assertFalse(other.claim_reminder(item["id"], "voice-one", "proactive"))
        self.assertTrue(other.claim_reminder(item["id"], "voice-two", "morning"))
        completed = other.complete(item["id"])["item"]
        self.assertFalse(completed["overdue"])

    def test_config_edit_is_idempotent_and_does_not_invent_completion(self):
        cfg = {**self.cfg, "id": "a" * 32}
        item = self.chores.save(cfg)["item"]
        self.now += 100
        same = self.chores.save(cfg)["item"]
        self.assertEqual(item, same)
        edited = self.chores.save({**cfg, "interval_days": 7})["item"]
        self.assertEqual(item["created_at"] + 7 * 86400, edited["due_at"])
        self.assertIsNone(edited["last_done_at"])
        self.assertNotEqual(item["revision"], edited["revision"])

    def test_completion_short_debounce_and_disable_snooze(self):
        item = self.chores.save(self.cfg)["item"]
        first = self.chores.complete(item["id"])["item"]
        self.now += 1
        self.assertEqual(first, self.chores.complete(item["id"])["item"])
        self.now = first["due_at"] + 1
        self.chores.snooze(item["id"], 2)
        self.assertEqual([], self.chores.due())
        self.now += 2 * 86400 + 1
        self.assertTrue(self.chores.due())
        self.chores.save({**self.cfg, "id": item["id"], "enabled": False})
        self.assertEqual([], self.chores.due())

    def test_paused_guest_forget_and_stale_delivery_gates(self):
        item = self.chores.save(self.cfg)["item"]
        self.now = item["due_at"] + 1
        self.owner.control({"paused": True})
        self.assertEqual([], self.chores.due())
        self.assertFalse(self.chores.claim_reminder(item["id"], "ignored", "morning"))
        self.owner.control({"paused": False, "guest": True})
        self.assertEqual([], self.chores.due())
        self.owner.control({"guest": False})
        self.chores.complete(item["id"])
        self.assertIsNone(self.chores.still_due(item["id"], item["due_at"], item["revision"]))
        self.assertFalse(
            self.chores.claim_reminder(
                item["id"], "stale", "proactive", expected_due_at=item["due_at"]
            )
        )
        self.assertIn("chores.item." + item["id"], str(self.owner.export()))
        self.owner.forget({"confirm": "forget_amadeus"})
        self.assertEqual([], self.chores.snapshot()["items"])
        with self.assertRaises(ValueError):
            self.chores.complete(item["id"])

    def test_fairness_prioritizes_chores_never_reminded(self):
        items = [
            self.chores.save({**self.cfg, "title": f"Invented task {i}"})["item"] for i in range(4)
        ]
        self.now = items[0]["due_at"] + 1
        for item in self.chores.due(limit=3):
            self.chores.claim_reminder(item["id"], "first-" + item["id"], "proactive")
        unreminded = self.chores.due(remind_only=True, limit=3)
        self.assertEqual(1, len(unreminded))
        self.now += 86401
        self.assertEqual(unreminded[0]["id"], self.chores.due(remind_only=True)[0]["id"])

    def test_tag_action_marks_only_selected_chore_and_learning_never_completes(self):
        item = self.chores.save(self.cfg)["item"]
        call = Mock()
        tags = Tags(
            self.path / "tags", lambda: [], call, clock=lambda: self.now, chores=self.chores
        )
        tags.save(
            {
                "tag_id": "invented-tag",
                "name": "Example task",
                "action": "chore_reminder",
                "chore_id": item["id"],
                "enabled": True,
            }
        )
        event = {"tag_id": "invented-tag", "event_id": "synthetic-1", "observed_at": self.now}
        tags.learn()
        self.assertEqual("registered_for_review", tags.scan(event)["status"])
        self.assertIsNone(self.chores.snapshot()["items"][0]["last_done_at"])
        self.now += 91
        event.update(event_id="synthetic-2", observed_at=self.now)
        result = tags.scan(event)
        self.assertEqual("chore_completed", result["status"])
        self.assertNotIn("title", result)
        call.assert_not_called()
        self.assertEqual("duplicate", tags.scan(event)["status"])
        self.chores.remove(item["id"])
        self.now += 4
        event.update(event_id="synthetic-3", observed_at=self.now)
        self.assertEqual("chore_unavailable", tags.scan(event)["status"])
        self.assertEqual([], self.chores.snapshot()["items"])

    def test_validation_and_owner_only_routes(self):
        for value in [True, 0, 366, 1.5]:
            with self.assertRaises(ValueError):
                self.chores.save({**self.cfg, "interval_days": value})
        bridge = SimpleNamespace(chores=self.chores, allowed_hosts={"localhost:8768"})

        def request(path, owner=True, data=None, origin=None):
            body = json.dumps(data or {}).encode()
            respond = Mock()
            h = SimpleNamespace(
                path=path,
                headers={
                    "Host": "localhost:8768",
                    "Content-Length": str(len(body)),
                    **({"Origin": origin} if origin else {}),
                },
                authorized=lambda: owner,
                connection=Mock(),
                rfile=io.BytesIO(body),
                respond=respond,
            )
            self.assertTrue(handle(h, bridge, post=data is not None))
            return respond.call_args.args

        self.assertEqual(403, request("/chores", owner=False)[0])
        self.assertEqual(403, request("/chores", origin="http://other.example")[0])
        self.assertEqual(200, request("/chores/save", data=self.cfg)[0])
        self.assertEqual(400, request("/chores/remove")[0])
        self.assertEqual(400, request("/chores/complete", data={"id": "invalid"})[0])

    def test_forgotten_chore_is_not_echoed_after_action_commit(self):
        from unittest.mock import patch

        original = self.chores.snapshot

        def forget_before_response():
            self.owner.forget({"confirm": "forget_amadeus"})
            return original()

        with patch.object(self.chores, "snapshot", side_effect=forget_before_response):
            response = self.chores.save(self.cfg)
        self.assertIsNone(response["item"])
        self.assertEqual("context_changed", response["state"])
        self.assertNotIn(self.cfg["title"], str(response))

    def test_chore_tool_is_read_only_and_respects_pause_guest(self):
        from okabebot.local_conversation import READ_TOOLS, acknowledgement

        item = self.chores.save(self.cfg)["item"]
        self.assertIn("get_chores", READ_TOOLS)
        self.assertEqual([], self.chores.context()["items"])
        context = self.chores.context(include_upcoming=True)
        self.assertEqual(item["title"], context["items"][0]["title"])
        self.assertNotIn("completion_ids", str(context))
        self.assertIn(item["title"], acknowledgement("get_chores", context))
        self.owner.control({"guest": True})
        self.assertEqual([], self.chores.context(True)["items"])

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from okabebot.amadeus import Store


class AmadeusTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.now = 2000000000
        self.store = Store(self.folder.name, sources=["synthetic"], clock=lambda: self.now)
        self.event = dict(
            source="synthetic",
            external_id="door-1",
            subject="person-a",
            kind="door",
            payload={"state": "open"},
            observed_at=self.now,
        )

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def test_duplicate_restart_and_conflict_preserve_original_provenance(self):
        first = self.store.observe(**self.event)
        self.assertEqual(self.store.observe(**self.event), dict(first, status="duplicate"))
        with self.assertRaises(ValueError):
            self.store.observe(**dict(self.event, payload={"state": "closed"}))
        self.store.close()
        self.store = Store(self.folder.name, sources=["synthetic"], clock=lambda: self.now)
        self.assertEqual(self.store.observe(**self.event)["status"], "duplicate")
        self.assertEqual(self.store.recall("person-a")["events"][0]["payload"], {"state": "open"})

    def test_subject_isolation_explicit_correction_and_forget(self):
        self.store.observe(**self.event)
        self.store.remember("person-a", "food.spice", "medium")
        self.store.remember("person-a", "food.spice", "mild")
        self.store.remember("person-b", "food.spice", "hot")
        self.assertEqual(self.store.recall("person-a")["preferences"][0]["value"], "mild")
        self.assertEqual(self.store.recall("person-b")["events"], [])
        self.assertEqual(self.store.forget("person-a"), 2)
        self.assertEqual(self.store.recall("person-a"), {"events": [], "preferences": []})
        self.assertEqual(self.store.recall("person-b")["preferences"][0]["value"], "hot")

    def test_retry_without_source_timestamp_keeps_first_observation_time(self):
        event = dict(self.event)
        event.pop("observed_at")
        first = self.store.observe(**event)
        self.now += 10
        self.assertEqual(self.store.observe(**event), dict(first, status="duplicate"))
        self.assertEqual(self.store.recall("person-a")["events"][0]["observed_at"], self.now - 10)

    def test_retention_hides_expired_rows_and_prunes_without_erasing_explicit_preference(self):
        self.store.observe(**self.event)
        self.store.remember("person-a", "subtitles", True)
        self.now += 31 * 86400
        self.assertEqual(self.store.recall("person-a")["events"], [])
        self.assertEqual(self.store.prune(), 1)
        self.assertEqual(self.store.observe(**self.event), {"status": "expired"})
        self.assertTrue(self.store.recall("person-a")["preferences"][0]["value"])

    def test_rejects_unallowed_sources_raw_fields_bad_states_and_nonfinite_values(self):
        for change, error in (
            ({"source": "unapproved"}, PermissionError),
            ({"payload": {"audio": "secret"}}, ValueError),
            ({"payload": {"state": "maybe"}}, ValueError),
            ({"observed_at": float("nan")}, ValueError),
            ({"observed_at": self.now + 301}, ValueError),
            ({"subject": "../../other"}, ValueError),
        ):
            with self.subTest(change=change), self.assertRaises(error):
                self.store.observe(**dict(self.event, **change))
        self.assertEqual(self.store.recall("person-a")["events"], [])

    def test_permissions_and_no_default_source(self):
        path = Path(self.folder.name) / "amadeus.sqlite3"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with tempfile.TemporaryDirectory() as other:
            store = Store(other)
            try:
                with self.assertRaises(PermissionError):
                    store.observe(**self.event)
            finally:
                store.close()
            Path(other).chmod(0o755)
            with self.assertRaises(PermissionError):
                Store(other)

    def test_cli_remember_recall_and_forget_are_local_and_durable(self):
        def command(*args):
            result = subprocess.run(
                [sys.executable, "-m", "okabebot.amadeus", "--folder", self.folder.name, *args],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)

        command("remember", "--subject", "trial-user", "--key", "subtitles", "--value", "true")
        self.assertTrue(command("recall", "--subject", "trial-user")["preferences"][0]["value"])
        self.assertEqual(command("forget", "--subject", "trial-user")["deleted"], 1)
        self.assertEqual(command("recall", "--subject", "trial-user")["preferences"], [])

"""Invented local drafts: leases, review versions, privacy and retention."""

from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from okabebot.amadeus import Store
from okabebot.amadeus_onboarding import SYSTEM, KEY
from okabebot.preparations import Preparations


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1900000000
        self.folder = Path(self.tmp.name)
        self.setup = dict(profile="invented", paused=False, guest=False)
        self.configure()
        self.jobs = Preparations(self.folder, clock=lambda: self.now)

    def configure(self):
        with closing(Store(self.folder)) as store:
            store.remember(SYSTEM, KEY, self.setup)

    def test_review_requires_current_revision_and_never_executes(self):
        job = self.jobs.start(provider="safeway")
        ready = self.jobs.change(job["id"], 1, "ready", items=["Oats", "oats", "Tea"])
        self.assertEqual(ready["items"], ["Oats", "Tea"])
        with self.assertRaises(ValueError):
            self.jobs.change(job["id"], 1, "save")
        saved = self.jobs.change(job["id"], 2, "save")
        self.assertEqual(saved["status"], "saved")
        self.assertFalse(self.jobs.snapshot()["execution_supported"])
        self.assertEqual(self.jobs.presentation(), {})

    def test_expired_worker_cannot_publish_and_projection_has_no_contents(self):
        job = self.jobs.start(title="Invented private list")
        self.assertEqual(
            set(self.jobs.presentation()), {"kind", "stage", "elapsed_seconds", "lease_seconds"}
        )
        self.now += 31
        self.assertEqual(self.jobs.presentation()["stage"], "blocked")
        with self.assertRaises(ValueError):
            self.jobs.change(job["id"], 1, "ready", items=["Tea"])

    def test_progress_renews_lease_and_resets_only_new_stage(self):
        job = self.jobs.start()
        self.now += 20
        self.jobs.change(job["id"], 1, "progress", stage="drafting")
        self.assertEqual(self.jobs.presentation()["elapsed_seconds"], 0)
        self.now += 20
        self.jobs.change(job["id"], 2, "progress", stage="drafting")
        self.assertEqual(self.jobs.presentation()["elapsed_seconds"], 20)
        with self.assertRaises(ValueError):
            self.jobs.change(job["id"], 3, "progress", stage="researching")

    def test_pause_hides_and_retention_still_deletes(self):
        self.jobs.start()
        self.setup["paused"] = True
        self.configure()
        self.assertEqual(self.jobs.presentation(), {})
        with self.assertRaises(PermissionError):
            self.jobs.start()
        self.now += 86401
        self.jobs.prune()
        self.setup["paused"] = False
        self.configure()
        self.assertEqual(self.jobs.snapshot()["jobs"], [])

    def test_changed_consent_blocks_old_work(self):
        job = self.jobs.start()
        self.setup["sources"] = ["calendar"]
        self.configure()
        with self.assertRaises(ValueError):
            self.jobs.change(job["id"], 1, "ready", items=["Tea"])

import datetime as dt
import tempfile
import unittest
from unittest.mock import patch

from okabebot.adapters.github_checks import poll
from okabebot.notifications import Inbox
from okabebot.sources import Sources


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.context = Sources(Inbox(self.tmp.name), self.tmp.name, {"github": "owner/repo"})
        self.old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
        self.now = dt.datetime.now(dt.timezone.utc).isoformat()

    def run_data(self, attempt=1, conclusion="failure", updated=None):
        return {
            "id": 42,
            "name": "CI",
            "run_number": 8,
            "run_attempt": attempt,
            "head_branch": "feature",
            "updated_at": updated or self.now,
            "conclusion": conclusion,
        }

    def test_baseline_no_historical_replay_then_failure_and_retry(self):
        with patch(
            "okabebot.adapters.github_checks.api",
            return_value=[{"workflow_runs": [self.run_data(updated=self.old)]}],
        ):
            poll(self.context)
        self.assertEqual(self.context.inbox.items(), [])
        self.context.state["github_checks"]["owner/repo"]["since"] = self.old
        with patch(
            "okabebot.adapters.github_checks.api",
            return_value=[{"workflow_runs": [self.run_data()]}],
        ):
            poll(self.context)
            poll(self.context)
        self.assertEqual(len(self.context.inbox.items()), 1)
        self.assertEqual(self.context.inbox.items()[0]["audio"], "chime")
        with patch(
            "okabebot.adapters.github_checks.api",
            return_value=[{"workflow_runs": [self.run_data(attempt=2)]}],
        ):
            poll(self.context)
        self.assertEqual(len(self.context.inbox.items()), 2)

    def test_partial_access_failure_preserves_cursor_and_other_repo_progress(self):
        self.context.settings["github"] = "all"
        self.context.state.update(
            github_checks_repositories={"at": 1e12, "names": ["owner/a", "owner/b"]},
            github_checks={"owner/a": {"since": self.old}, "owner/b": {"since": self.old}},
        )

        def api(path):
            if "owner/a/" in path:
                raise RuntimeError("private credential must not leak")
            return [
                {"workflow_runs": [self.run_data(conclusion="success")]},
                {"workflow_runs": [self.run_data()]},
            ]

        with (
            patch("okabebot.adapters.github_checks.api", side_effect=api),
            self.assertRaises(RuntimeError),
        ):
            poll(self.context)
        self.assertEqual(self.context.state["github_checks"]["owner/a"]["since"], self.old)
        self.assertNotEqual(self.context.state["github_checks"]["owner/b"]["since"], self.old)
        self.assertEqual(len(self.context.inbox.items()), 1)

    def test_first_failure_keeps_baseline_for_recovery(self):
        with (
            patch("okabebot.adapters.github_checks.api", side_effect=OSError()),
            self.assertRaises(RuntimeError),
        ):
            poll(self.context)
        self.assertIn("owner/repo", self.context.state["github_checks"])

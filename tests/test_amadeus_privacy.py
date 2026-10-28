import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check-amadeus-privacy.py"
spec = importlib.util.spec_from_file_location("amadeus_privacy", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class PrivacyGuardTests(unittest.TestCase):
    def test_known_private_artifacts_blocked_but_core_and_declarative_docs_allowed(self):
        self.assertEqual(
            guard.private_paths(
                [
                    "okabebot/amadeus_coaching.py",
                    "docs/amadeus-progress.md",
                    "tests/test_amadeus.py",
                ]
            ),
            [],
        )
        for path in (
            ".local/private.json",
            "amadeus-trials/session.json",
            "nested/participant-data/preferences.json",
            "trial-results/summary.md",
        ):
            self.assertEqual(guard.private_paths([path]), [path])

    def test_forced_staged_artifacts_rejected_without_printing_private_path(self):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(["git", "init", "-q", folder], check=True)
            path = Path(folder) / "amadeus-trials" / "private-person.json"
            path.parent.mkdir()
            path.write_text('{"synthetic":"guard fixture"}')
            subprocess.run(["git", "add", str(path)], cwd=folder, check=True)
            result = subprocess.run(
                [sys.executable, str(SCRIPT)], cwd=folder, text=True, capture_output=True
            )
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("private-person", result.stderr)
            path.unlink()
            subprocess.run(["git", "add", "-u"], cwd=folder, check=True)
            result = subprocess.run(
                [sys.executable, str(SCRIPT)], cwd=folder, text=True, capture_output=True
            )
            self.assertEqual(result.returncode, 0)

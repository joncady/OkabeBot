"""Read-only collector is bounded and never substitutes for an offline image."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("backup", "scripts/backup-companion-config.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def test_private_files_no_mutation_no_ssh_verification_bypass(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(backup.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, b"synthetic", b"")
            path = Path(tmp) / "private"
            backup.collect("pi@pi.example", Path("/private/key"), path, True)
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            for filename in ("diagnostics.json", "configuration.tar.gz"):
                self.assertEqual((path / filename).stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                len(json.loads((path / "diagnostics.json").read_text())), len(backup.COMMANDS)
            )
            for call in run.call_args_list:
                argv = call.args[0]
                self.assertIn("StrictHostKeyChecking=yes", argv)
                self.assertFalse(set(argv) & {"sudo", "dd", "reboot", "apt", "rm"})
            with self.assertRaises(ValueError):
                backup.collect("pi@pi.example", Path("key"), path)
        for target in ("-option@host", "pi@host;reboot", "pi@host $(command)"):
            with self.assertRaises(ValueError):
                backup.connection(target, "key")

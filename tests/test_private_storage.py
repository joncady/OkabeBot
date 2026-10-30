import json
import os
from pathlib import Path
import tempfile
import unittest
from okabebot.private_storage import DEFAULTS, PrivateStorage


class PrivateStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 2_000_000_000
        self.manager = PrivateStorage(self.root, clock=lambda: self.now)

    def file(self, name, body=b"old", age=86400 * 30):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        os.utime(path, (self.now - age, self.now - age))
        return path

    def test_disabled_policy_never_removes_or_trims(self):
        path = self.file("audio/clip.wav")
        log = self.file("runtime/controller.log")
        self.manager.cleanup()
        self.assertTrue(path.exists())
        self.assertEqual(b"old", log.read_bytes())
        self.assertFalse(self.manager.snapshot()["policy"]["enabled"])

    def test_limits_remove_old_recordings_but_preserve_active_and_protected_content(self):
        old = self.file("audio/old.wav")
        active = self.file("audio/active.wav", age=20)
        protected = [
            self.file(p)
            for p in [
                "amadeus/amadeus.sqlite3",
                "models/model.wav",
                "voice-references/ref.wav",
                "exports/export.json",
                "rollback/clip.wav",
                "audio/credentials.json",
            ]
        ]
        self.manager.configure({**DEFAULTS, "enabled": True})
        self.manager.cleanup()
        self.assertFalse(old.exists())
        self.assertTrue(active.exists())
        self.assertTrue(all(p.exists() for p in protected))
        self.assertNotIn("old.wav", json.dumps(self.manager.snapshot()))

    def test_log_copytruncate_keeps_open_append_descriptor_working(self):
        log = self.file("runtime/controller.log", b"x" * (1024 * 1024) + b"tail", age=0)
        self.manager.configure({**DEFAULTS, "enabled": True, "logs_mb": 1})
        with log.open("ab") as writer:
            self.manager.cleanup()
            writer.write(b"after")
            writer.flush()
        self.assertEqual(1024 * 1024 + 5, log.stat().st_size)
        self.assertTrue(log.read_bytes().endswith(b"tailafter"))

    def test_recording_budget_evicts_oldest_eligible_first(self):
        a = self.file("recordings/older.mp4", b"a" * 800000, age=1000)
        b = self.file("recordings/newer.mp4", b"b" * 800000, age=500)
        self.manager.configure({**DEFAULTS, "enabled": True, "recordings_mb": 1})
        self.manager.cleanup()
        self.assertFalse(a.exists())
        self.assertTrue(b.exists())

    def test_symlink_and_hardlinked_log_never_modify_external_files(self):
        outside = self.file("protected/data", b"keep")
        (self.root / "runtime").mkdir()
        (self.root / "runtime/link.log").symlink_to(outside)
        os.link(outside, self.root / "runtime/hard.log")
        (self.root / "recordings").symlink_to(self.root / "protected", target_is_directory=True)
        self.manager.configure({**DEFAULTS, "enabled": True})
        self.manager.cleanup()
        self.assertEqual(b"keep", outside.read_bytes())
        self.assertTrue((self.root / "runtime/link.log").is_symlink())

    def test_busy_and_invalid_policy_fail_closed(self):
        path = self.file("audio/old.wav")
        self.manager.configure({**DEFAULTS, "enabled": True})
        self.manager.cleanup(busy=True)
        self.assertTrue(path.exists())
        self.manager.path.write_text(json.dumps({"enabled": True, "logs_mb": -1}))
        self.manager.cleanup()
        self.assertTrue(path.exists())
        with self.assertRaises(ValueError):
            self.manager.configure({**DEFAULTS, "recordings_days": False})

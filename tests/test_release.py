import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_check", ROOT / "scripts/check-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_audit_rejects_private_state_and_credentials_without_printing_them(self):
        with tempfile.TemporaryDirectory() as folder:
            wheel = Path(folder) / "example.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(".local/notification-token", "private")
                archive.writestr("package/config.txt", "sk-" + "a" * 30)
            errors = release.audit(wheel)
            self.assertTrue(any("Private/unsafe path" in e for e in errors))
            self.assertTrue(any("Possible credential" in e for e in errors))
            self.assertNotIn("sk-" + "a" * 30, "\n".join(errors))

    def test_setup_skill_references_and_invocation_are_portable(self):
        import yaml

        skill = ROOT / ".agents/skills/okabebot-setup/SKILL.md"
        raw = skill.read_text()
        front = yaml.safe_load(raw.split("---", 2)[1])
        self.assertEqual(front["name"], "okabebot-setup")
        for target in re.findall(r"\]\(([^)]+)\)", raw):
            if "://" not in target:
                self.assertTrue((skill.parent / target).resolve().exists(), target)
        interface = yaml.safe_load((skill.parent / "agents/openai.yaml").read_text())
        self.assertIn("$okabebot-setup", interface["interface"]["default_prompt"])

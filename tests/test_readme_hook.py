import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "readme_hook", Path(__file__).resolve().parents[1] / "scripts/check-readme.py"
)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class ReadmeHookTests(unittest.TestCase):
    def test_update_or_explained_review_required(self):
        self.assertFalse(hook.check(["okabebot/server.py"], "Fix a tool"))
        self.assertTrue(hook.check(["README.md", "okabebot/server.py"], "Document a tool"))
        self.assertTrue(
            hook.check(
                ["okabebot/server.py"],
                "Fix\n\nREADME-Reviewed: Internal fix; public setup is unchanged.",
            )
        )
        self.assertFalse(hook.check(["okabebot/server.py"], "README-Reviewed: yes"))

    def test_topology_review_is_separate_from_readme_review(self):
        self.assertFalse(hook.topology_check(["README.md", "pi/voice_service.py"], "Update"))
        self.assertTrue(hook.topology_check(["docs/deployment.md", "pi/service.py"], "Update"))
        self.assertFalse(hook.topology_check(["okabebot/config.py"], "Topology-Reviewed: yes"))
        self.assertTrue(
            hook.topology_check(
                ["okabebot/local_worker.py"],
                "Fix\n\nTopology-Reviewed: Internal parsing fix; worker location and model are unchanged.",
            )
        )

    def test_integration_and_launcher_changes_require_review_but_art_does_not(self):
        for path in (
            "infra/github-relay/lambda.py",
            "examples/home-assistant/door_welcome.yaml",
            "scripts/start-mac.sh",
            "okabebot/adapters/media.py",
            "docs/devices.md",
        ):
            with self.subTest(path=path):
                self.assertFalse(hook.topology_check([path], "Change"))
        self.assertTrue(hook.topology_check(["docs/okabe.png", "tests/test_character.py"], "Art"))

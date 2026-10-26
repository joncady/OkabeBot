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

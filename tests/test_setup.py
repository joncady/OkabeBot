from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from okabebot.config import DEFAULTS
from okabebot.doctor import check


class SetupTests(unittest.TestCase):
    def test_doctor_selects_optional_dependencies_without_touching_hardware(self):
        config = deepcopy(DEFAULTS)
        config["state_dir"] = tempfile.gettempdir()
        config["spotify"]["source"] = "cast"
        with (
            patch(
                "okabebot.doctor.importlib.util.find_spec", return_value=object()
            ) as dependencies,
            patch("okabebot.doctor.shutil.which", return_value="/installed"),
        ):
            results = check(config)
        self.assertTrue(all(r["ok"] for r in results))
        self.assertIn("pychromecast", [c.args[0] for c in dependencies.call_args_list])
        self.assertFalse(any(r["name"] == "display" for r in results))

    def test_linux_launcher_preserves_config_paths_and_bridge_arguments(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="setup with spaces ") as folder:
            temp = Path(folder)
            config = temp / "personal config.json"
            config.write_text("{}")
            uname = temp / "uname"
            uname.write_text("#!/bin/sh\nprintf 'Linux\\n'\n")
            uname.chmod(0o755)
            fake = temp / "fake-python"
            out = temp / "args.json"
            helper = temp / "capture-args.py"
            helper.write_text(
                "import json,os,sys\nfrom pathlib import Path\nPath(os.environ['SETUP_TEST_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
            )
            fake.write_text('#!/bin/sh\nexec "$SETUP_TEST_PYTHON" "$SETUP_TEST_HELPER" "$@"\n')
            fake.chmod(0o755)
            env = dict(
                os.environ,
                PATH=str(temp) + os.pathsep + os.environ["PATH"],
                OKABEBOT_PYTHON=str(fake),
                SETUP_TEST_ARGS=str(out),
                SETUP_TEST_PYTHON=sys.executable,
                SETUP_TEST_HELPER=str(helper),
            )
            subprocess.run(
                [str(root / "scripts/start-linux.sh"), str(config), "--", "--port", "9876"],
                env=env,
                check=True,
            )
            self.assertEqual(
                json.loads(out.read_text()),
                ["-m", "okabebot.bridge", "--config", str(config), "--port", "9876"],
            )
            subprocess.run(
                [str(root / "scripts/start-linux.sh"), str(config), "--check"], env=env, check=True
            )
            self.assertEqual(json.loads(out.read_text())[:2], ["-m", "okabebot.doctor"])
            self.assertIn("--devices", json.loads(out.read_text()))

import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'mac_install', Path(__file__).resolve().parents[1] / 'scripts/install-mac.py'
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class MacInstallationTests(unittest.TestCase):
    def test_environment_copy_does_not_import_development_editable_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            site = source / 'lib/python3.11/site-packages'
            site.mkdir(parents=True)
            (site / '__editable__old.pth').write_text('import original_documents_checkout')
            (site / '__editable__old_finder.py').write_text('private old path')
            (site / 'dependency.py').write_text('safe_dependency = True')
            target = root / 'installation/.venv'
            installer.copy_environment(source, target)
            installed_site = target / 'lib/python3.11/site-packages'
            self.assertEqual(list(installed_site.glob('__editable__*')), [])
            self.assertEqual((installed_site / 'okabebot-runtime.pth').read_text().strip(),
                             str(target.parent))
            self.assertTrue((installed_site / 'dependency.py').exists())
            self.assertTrue((site / '__editable__old.pth').exists())

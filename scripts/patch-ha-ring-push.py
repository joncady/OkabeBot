#!/usr/bin/env python3
"""Optional HA 2026.10.4/firebase-messaging 0.4.5 push compatibility backport.

Read-only by default; --apply backs up inside /config before changing the container
layer. A HA restart is required. Container replacement removes the patch.
Header selection follows the problem documented by firebase-messaging PR #43;
malformed encrypted packets are acknowledged/skipped with a rate-limited warning.
No camera model/capability mappings or account credentials are changed.
"""

import argparse
import ast
import inspect
import subprocess


def webpush_parameter(header, name):
    """Select a named parameter, preserving base64 padding, never log headers."""
    for part in header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name and value.strip():
            value = value.strip().strip('"')
            return value + "=" * (-len(value) % 4)
    raise ValueError("Missing Web Push parameter")


def patch_source(source, helper_source=None):
    marker = "# OkabeBot Web Push compatibility v1"
    if marker in source:
        return source
    replacements = {
        '        crypto_key = self._app_data_by_key(msg, "crypto-key")[3:]  # strip dh=': '        crypto_key = webpush_parameter(self._app_data_by_key(msg, "crypto-key"), "dh")',
        '        salt = self._app_data_by_key(msg, "encryption")[5:]  # strip salt=': '        salt = webpush_parameter(self._app_data_by_key(msg, "encryption"), "salt")',
        "            self._handle_data_message(msg)": '            try:\n                self._handle_data_message(msg)\n            except (ValueError, UnicodeError):\n                self._log_warn_with_limit("Skipped malformed encrypted push; listener remains active")',
    }
    if source.count("class FcmPushClient:") != 1 or any(source.count(k) != 1 for k in replacements):
        raise ValueError("Unsupported push client source; no changes made")
    for old, new in replacements.items():
        source = source.replace(old, new)
    helper = helper_source or inspect.getsource(webpush_parameter)
    source = source.replace(
        "class FcmPushClient:", marker + "\n" + helper + "\n\nclass FcmPushClient:"
    )
    ast.parse(source)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="okabebot-home-assistant")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    code = (
        """import ast,inspect,json,pathlib,shutil,time
from importlib.metadata import version
from homeassistant.const import __version__
"""
        + inspect.getsource(webpush_parameter)
        + "\n"
        + inspect.getsource(patch_source)
        + f"""
if __version__ != '2026.10.4' or version('firebase-messaging') != '0.4.5':
    raise SystemExit('Unvalidated HA/dependency version; no changes made')
import firebase_messaging.fcmpushclient as module
path=pathlib.Path(module.__file__)
source=path.read_text();updated=patch_source(source, {inspect.getsource(webpush_parameter)!r})
if source == updated:
    print(json.dumps({{'status':'already_present'}}))
elif {args.apply!r}:
    backup=pathlib.Path('/config/.local-compat-backups')/('ring-push-'+str(time.time_ns()))
    backup.mkdir(parents=True);shutil.copy2(path,backup/path.name)
    temporary=path.with_suffix('.py.new');temporary.write_text(updated);temporary.replace(path)
    print(json.dumps({{'status':'patched','restart_required':True}}))
else:
    print(json.dumps({{'status':'patch_needed','changed':False}}))
"""
    )
    subprocess.run(
        ["docker", "exec", "-i", args.container, "python", "-"], input=code, text=True, check=True
    )


if __name__ == "__main__":
    main()

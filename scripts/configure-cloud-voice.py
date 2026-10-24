#!/usr/bin/env python3
"""Privately save an API key for the controller's systemd user service."""

import getpass
import os
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

key = getpass.getpass("OpenAI API key (hidden; separate API billing applies): ").strip()
if not key or any(c in key for c in "\r\n\x00"):
    raise SystemExit("No valid key supplied; nothing changed.")
try:
    request = Request(
        "https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + key}
    )
    with urlopen(request, timeout=15):
        pass
except HTTPError as exc:
    raise SystemExit("Key verification failed (HTTP %s); nothing changed." % exc.code)
except URLError:
    raise SystemExit("Could not reach OpenAI to verify the key; nothing changed.")
root = Path(__file__).resolve().parent.parent
secret = root / "state" / "openai.env"
secret.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, "w") as out:
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    out.write('OPENAI_API_KEY="' + escaped + '"\n')
drop = Path.home() / ".config/systemd/user/okabebot.service.d"
drop.mkdir(parents=True, exist_ok=True)
(drop / "cloud.conf").write_text("[Service]\nEnvironmentFile=" + str(secret) + "\n")
os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid()))
subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
subprocess.run(["systemctl", "--user", "restart", "okabebot"], check=True)
print("Key saved privately. Select Cloud in the control page after startup.")

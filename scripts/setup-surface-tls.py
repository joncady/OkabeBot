#!/usr/bin/env python3
"""Create a private local CA and LAN server certificate; never installs trust.

Run once, explicitly trust the CA certificate on the phone, then configure the
printed web.tls paths. No public exposure or account connection is created.
"""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--hostname", required=True, help="Stable local DNS name, for example computer.local"
)
parser.add_argument("--ip", required=True, help="Controller LAN IPv4 address")
parser.add_argument("--directory", default=".local/surface-tls")
args = parser.parse_args()

ipaddress.IPv4Address(args.ip)
if not re.fullmatch(r"[A-Za-z0-9-]+\.local", args.hostname):
    parser.error("Use a local mDNS hostname")
folder = Path(args.directory).expanduser().resolve()
folder.mkdir(parents=True, exist_ok=True)
os.chmod(folder, 0o700)
if any((folder / name).exists() for name in ("ca.key", "ca.pem", "server.key", "server.pem")):
    parser.error("Certificates already exist; preserve them and reuse the current CA")


def run(*command):
    subprocess.run(
        ["openssl", *command],
        cwd=folder,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


(folder / "ca.cnf").write_text(
    "[req]\ndistinguished_name=dn\nx509_extensions=ca\nprompt=no\n[dn]\nCN=Little Lab local CA\n[ca]\nbasicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n"
)
run(
    "req",
    "-x509",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-keyout",
    "ca.key",
    "-out",
    "ca.pem",
    "-days",
    "3650",
    "-subj",
    "/CN=Little Lab local CA",
    "-extensions",
    "ca",
    "-config",
    "ca.cnf",
)
run(
    "req",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-keyout",
    "server.key",
    "-out",
    "server.csr",
    "-subj",
    "/CN=" + args.hostname,
)
(folder / "server.ext").write_text(
    "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:"
    + args.hostname
    + ",DNS:localhost,IP:"
    + args.ip
    + ",IP:127.0.0.1\n"
)
run(
    "x509",
    "-req",
    "-in",
    "server.csr",
    "-CA",
    "ca.pem",
    "-CAkey",
    "ca.key",
    "-CAcreateserial",
    "-out",
    "server.pem",
    "-days",
    "365",
    "-extfile",
    "server.ext",
)
for name in ("ca.key", "server.key"):
    os.chmod(folder / name, 0o600)
print(
    json.dumps(
        {
            "web": {
                "allowed_hosts": [args.hostname + ":8768", args.hostname + ":8780"],
                "tls": {
                    "port": 8780,
                    "certificate": str(folder / "server.pem"),
                    "ca_certificate": str(folder / "ca.pem"),
                    "key": str(folder / "server.key"),
                },
            }
        },
        indent=2,
    )
)
print(
    "Phone trust is manual. Transfer only ca.pem, never either private key. This CA grants certificate trust: keep its key private."
)

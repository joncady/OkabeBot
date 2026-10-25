"""Persistent, publish-only credentials for local notification integrations."""

import hmac
import os
from pathlib import Path
import secrets


def notification_token(folder):
    path = Path(folder) / "notification-token"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        token = path.read_text().strip()
        if len(token) < 32:
            raise ValueError("Invalid notification integration token")
        return token
    token = secrets.token_urlsafe(32)
    with os.fdopen(fd, "w") as stream:
        stream.write(token)
    return token


def may_publish(path, host, allowed_hosts, supplied, expected):
    return (
        path == "/notifications"
        and host in allowed_hosts
        and bool(supplied)
        and hmac.compare_digest(supplied, expected)
    )

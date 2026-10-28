"""Narrow MCP projections over the running controller's existing API."""

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from .config import state_dir


def request(path="/state", payload=None, timeout=10):
    try:
        control = json.loads((state_dir() / "ptt" / "control.json").read_text())
        url = urlsplit(control["url"])
        if url.scheme != "http" or not url.fragment or not url.port:
            raise ValueError("Invalid control URL")
        # The controller may bind only its configured LAN address, not loopback.
        target = "http://%s%s" % (url.netloc, path)
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(
            target,
            data=data,
            headers={"X-Hardware-Token": url.fragment, "Content-Type": "application/json"},
        )
        with urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except Exception:
        raise ValueError(
            "Controller unavailable or request rejected; check the dashboard. Do not blindly retry actions."
        ) from None


def projection(*keys):
    state = request()
    return {key: state.get(key) for key in keys}

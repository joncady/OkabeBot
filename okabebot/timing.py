"""Small atomic snapshots shared by the controller and MCP process."""

import json
import tempfile
import time
from pathlib import Path
from .config import state_dir


def write(name, values):
    folder = state_dir() / "timing"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as f:
        json.dump(dict(values, updated_at=time.time()), f)
        temp = Path(f.name)
    temp.replace(folder / (name + ".json"))


def read(name):
    try:
        return json.loads((state_dir() / "timing" / (name + ".json")).read_text())
    except (OSError, ValueError):
        return {}

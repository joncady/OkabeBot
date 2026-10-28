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


def append_turn(folder, clip_id, values):
    """Bounded private timing history; no utterance or notification text."""
    import sqlite3

    path = Path(folder) / "turn-timings.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY,completed REAL,payload TEXT)"
        )
        db.execute(
            "INSERT OR REPLACE INTO turns VALUES (?,?,?)",
            (clip_id, time.time(), json.dumps(dict(values, clip_id=clip_id))),
        )
        db.execute(
            "DELETE FROM turns WHERE id NOT IN (SELECT id FROM turns ORDER BY completed DESC LIMIT 200)"
        )


def recent_turns(folder, limit=10):
    import sqlite3

    path = Path(folder) / "turn-timings.sqlite3"
    if not path.exists():
        return []
    try:
        with sqlite3.connect(path) as db:
            rows = db.execute(
                "SELECT payload FROM turns ORDER BY completed DESC LIMIT ?",
                (min(50, max(1, limit)),),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
    except (sqlite3.Error, ValueError):
        return []

"""Private exact-session launch receipts; never infer ownership from an app name."""

from .presence_control import read, write


class Ownership:
    def __init__(self, path=None):
        from pathlib import Path

        self.path = Path(path) if path is not None else None
        value = read(self.path, None) if self.path is not None and self.path.exists() else {}
        self.invalid = not isinstance(value, dict)
        self.sessions = (
            {
                location: session
                for location, session in value.items()
                if isinstance(location, str) and isinstance(session, str) and location and session
            }
            if isinstance(value, dict)
            else {}
        )

        self.invalid |= isinstance(value, dict) and len(value) != len(self.sessions)

    def remember(self, location, session):
        if not isinstance(session, str) or not session:
            return
        self.sessions[location] = session
        self._save()

    def forget(self, location, session):
        if self.sessions.get(location) == session:
            del self.sessions[location]
            self._save()

    def _save(self):
        if self.invalid:
            raise ValueError("Saved Cast ownership needs review before replacement")
        if self.path is not None:
            write(self.path, self.sessions)

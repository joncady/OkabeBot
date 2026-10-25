"""Notification source coordinator; providers own fetching, not delivery."""

import json
from pathlib import Path
from .adapters.notifications import BUILTIN_ADAPTERS
from .adapters.github import poll as poll_github
from .adapters.calendar_feed import poll as poll_calendar


class Sources:
    def __init__(self, inbox, folder, settings, adapters=None):
        self.adapters = tuple(BUILTIN_ADAPTERS if adapters is None else adapters)
        self.inbox, self.settings = inbox, settings
        self.path = Path(folder) / "notification-sources.json"
        try:
            self.state = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.state = {}
        self.errors = {}

    def poll(self):
        for adapter in self.adapters:
            name = adapter.name
            try:
                if not adapter.enabled(self):
                    continue
                adapter.poll(self)
                self.errors.pop(name, None)
            except Exception:
                # Feed URLs and provider responses may contain private credentials.
                self.errors[name] = (
                    name + " sync failed; check its private configuration and access"
                )
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        tmp.replace(self.path)

    def github(self):
        return poll_github(self)

    def calendar(self):
        return poll_calendar(self)

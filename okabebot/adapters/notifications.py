"""Small polling adapter contract; delivery policy belongs to Inbox/Bridge."""

from dataclasses import dataclass
from typing import Callable, Protocol
from .github import poll as github
from .calendar_feed import poll as calendar
from .github_checks import poll as github_checks


class NotificationAdapter(Protocol):
    name: str

    def enabled(self, context) -> bool: ...
    def poll(self, context) -> None: ...


@dataclass(frozen=True)
class PollingAdapter:
    name: str
    callback: Callable
    setting: str = ""

    def enabled(self, context):
        return bool(context.settings.get(self.setting or self.name))

    def poll(self, context):
        self.callback(context)


BUILTIN_ADAPTERS = (
    PollingAdapter("github", github),
    PollingAdapter("calendar", calendar),
    PollingAdapter("github_checks", github_checks, "github"),
)

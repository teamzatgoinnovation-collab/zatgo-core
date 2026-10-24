"""Notification architecture for MyBis: a pure diff and a channel interface -- no transport is wired here.

`unread` says which items the user has not seen yet: an item's fingerprint (id + company + severity + period start) is stable while
the condition persists and changes when it escalates, so "new or worse" is a set difference. The in-app badge uses it today (the
app sends the fingerprints it has already shown). A scheduled job can later call `dispatch` for each user with whatever `seen` set
it keeps and a `NotificationChannel` for push, e-mail or chat; adding a channel does not touch the engine, the API or the app.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from zatgo_core.services.mybis.insights import RANK


def unread(items: Iterable[dict[str, Any]], seen: Iterable[str], min_severity: str = "low") -> list[dict[str, Any]]:
    """Items not yet seen whose severity is at least `min_severity` (critical > high > medium > low)."""
    limit = RANK.get(min_severity, RANK["low"])
    seen_set = set(seen)
    # An app may send back full fingerprints or the short `sid` the feed gave each item (keeps the request small).
    return [i for i in items if i["fingerprint"] not in seen_set and i.get("sid") not in seen_set and RANK[i["severity"]] <= limit]


class NotificationChannel(ABC):
    name: str

    @abstractmethod
    def deliver(self, user: str, items: list[dict[str, Any]]) -> int:
        """Send `items` to `user`; return how many were delivered."""


class InAppChannel(NotificationChannel):
    """The badge and the Alerts screen read the feed directly, so there is nothing to push."""

    name = "in_app"

    def deliver(self, user: str, items: list[dict[str, Any]]) -> int:
        return len(items)


CHANNELS: dict[str, NotificationChannel] = {InAppChannel.name: InAppChannel()}


def dispatch(user: str, items: Iterable[dict[str, Any]], seen: Iterable[str], min_severity: str = "low", channels: Iterable[str] | None = None) -> dict[str, int]:
    """Deliver the unread items through the named channels (default: all registered); returns delivered counts per channel."""
    fresh = unread(items, seen, min_severity)
    out: dict[str, int] = {}
    for name in channels or CHANNELS:
        out[name] = CHANNELS[name].deliver(user, fresh) if fresh else 0
    return out

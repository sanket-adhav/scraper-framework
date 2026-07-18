"""Minimal synchronous event bus — the Plan-03 stub of the real bus (Plan 08).

Listeners can never break the pipeline: their exceptions are swallowed and
counted, and they are never in the persist path.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from core.events.types import Event

Listener = Callable[[Event], None]


class EventBus:
    """Delivers published events to subscribed listeners, one by one, safely."""

    def __init__(self) -> None:
        """Starts with no listeners and a zero error count."""
        self._listeners: dict[str, list[Listener]] = defaultdict(list)
        self.listener_errors = 0

    def subscribe(self, event_type: str, listener: Listener) -> None:
        """Registers a listener for one event type ('*' means every event)."""
        self._listeners[event_type].append(listener)

    def publish(self, event: Event) -> None:
        """Sends the event to matching listeners; a crashing listener is counted, not raised."""
        for listener in self._listeners[event.type] + self._listeners["*"]:
            try:
                listener(event)
            except Exception:  # noqa: BLE001 — listeners must never break the pipeline
                self.listener_errors += 1

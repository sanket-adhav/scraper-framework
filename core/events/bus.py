"""The event bus (plan2.md §10, §14).

Listeners can never break the pipeline: their exceptions are caught and counted,
never propagated, and listeners are never in the persist path. Both sync and
async listeners are supported; async ones are dispatched fire-and-forget so
publishing never blocks the scrape.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from core.events.types import Event

logger = logging.getLogger("scraper.events")

SyncListener = Callable[[Event], None]
AsyncListener = Callable[[Event], Awaitable[None]]
Listener = SyncListener | AsyncListener


class EventBus:
    """Delivers published events to subscribed listeners, isolating their failures."""

    def __init__(self) -> None:
        """Starts with no listeners and a zero error count."""
        self._listeners: dict[str, list[Listener]] = defaultdict(list)
        self.listener_errors = 0
        self._background: set[asyncio.Task[None]] = set()

    def subscribe(self, event_type: str, listener: Listener) -> None:
        """Registers a listener for one event type ('*' means every event)."""
        self._listeners[event_type].append(listener)

    def publish(self, event: Event) -> None:
        """Sends the event to matching listeners; a crashing listener is counted, not raised.
        Async listeners are scheduled without blocking when a loop is running."""
        for listener in self._listeners.get(event.type, []) + self._listeners.get("*", []):
            self._deliver(listener, event)

    def _deliver(self, listener: Listener, event: Event) -> None:
        """Calls one listener safely — inline for sync, scheduled for async."""
        try:
            result = listener(event)
            if asyncio.iscoroutine(result):
                self._schedule(result)
        except Exception:  # noqa: BLE001 — listeners must never break the pipeline
            self.listener_errors += 1
            logger.warning("event listener failed for %s", event.type, exc_info=True)

    def _schedule(self, coro: Awaitable[None]) -> None:
        """Runs an async listener in the background, swallowing and counting its errors."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._guard(coro))  # no loop: run to completion now
            return
        task = loop.create_task(self._guard(coro))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _guard(self, coro: Awaitable[None]) -> None:
        """Awaits an async listener, converting any failure into a counted error."""
        try:
            await coro
        except Exception:  # noqa: BLE001 — same isolation for async listeners
            self.listener_errors += 1
            logger.warning("async event listener failed", exc_info=True)

    async def drain(self) -> None:
        """Waits for in-flight async listeners to finish (used at job end / in tests)."""
        while self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

"""Alert event listener (plan2.md §10).

Watches for trouble — block-rate spikes, validation-failure spikes, circuit
opens — and fires an alert (a webhook by default) when a configured threshold
is crossed. The sender is injectable so tests assert without a real webhook.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from core.events.types import BLOCK_DETECTED, CIRCUIT_OPENED, VALIDATION_FAILED, Event

AlertSender = Callable[[str], None]


class AlertListener:
    """Counts trouble events per plugin and alerts when a threshold is exceeded."""

    def __init__(
        self,
        sender: AlertSender,
        block_threshold: int = 5,
        validation_threshold: int = 20,
    ) -> None:
        """Remembers the alert sender and the counts at which to fire."""
        self._sender = sender
        self._block_threshold = block_threshold
        self._validation_threshold = validation_threshold
        self._blocks: dict[str, int] = defaultdict(int)
        self._validation: dict[str, int] = defaultdict(int)
        self._fired: set[str] = set()

    def __call__(self, event: Event) -> None:
        """Tallies the event and sends an alert the first time a threshold is crossed."""
        plugin = str(event.payload.get("plugin", "-"))
        if event.type == BLOCK_DETECTED:
            self._blocks[plugin] += 1
            self._maybe_fire(
                f"block:{plugin}",
                self._blocks[plugin] >= self._block_threshold,
                f"block-rate spike for {plugin}: {self._blocks[plugin]} blocks",
            )
        elif event.type == VALIDATION_FAILED:
            self._validation[plugin] += len(event.payload.get("fields", []) or [1])
            self._maybe_fire(
                f"validation:{plugin}",
                self._validation[plugin] >= self._validation_threshold,
                f"validation-failure spike for {plugin}: {self._validation[plugin]} failures",
            )
        elif event.type == CIRCUIT_OPENED:
            self._maybe_fire(
                f"circuit:{plugin}:{event.payload.get('domain')}",
                True,
                f"circuit opened for {event.payload.get('domain')}",
            )

    def _maybe_fire(self, key: str, crossed: bool, message: str) -> None:
        """Fires the alert once per key when its threshold is first crossed."""
        if crossed and key not in self._fired:
            self._fired.add(key)
            self._sender(message)

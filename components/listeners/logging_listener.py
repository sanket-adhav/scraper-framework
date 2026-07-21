"""Structured-logging event listener (plan2.md §10).

Logging is now just a bus subscriber — proving the decoupling: nothing in the
pipeline calls the logger directly; it only emits events, and this listener
turns them into structured log lines.
"""

from __future__ import annotations

import logging

from core.events.types import Event


class LoggingListener:
    """Writes one structured log line per event, keyed by trace id."""

    def __init__(self, logger_name: str = "scraper.pipeline") -> None:
        """Uses (or creates) the named logger for pipeline event logs."""
        self._logger = logging.getLogger(logger_name)

    def __call__(self, event: Event) -> None:
        """Logs the event type and payload at a level matching its severity.
        If a stage failure was skipped gracefully per error policy, downgrade to INFO."""
        is_warning = _is_bad(event.type)
        if is_warning and (
            event.payload.get("action") == "skip"
            or (event.type == "validation.failed" and not event.payload.get("has_record"))
        ):
            is_warning = False
            
        level = logging.WARNING if is_warning else logging.INFO
        self._logger.log(
            level, "event %s", event.type, extra={"event": event.type, **dict(event.payload)}
        )


def _is_bad(event_type: str) -> bool:
    """True for event types that signal trouble worth a WARNING."""
    return any(
        marker in event_type
        for marker in ("failed", "quarantined", "block", "circuit.opened", "retrying")
    )

"""Checkpoint model for incremental (only-what-changed) scraping — plan2.md §16.

Only the data shape and store contract live here now; the real change-detection
logic arrives in Plan 09.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Where one source's incremental scraping left off."""

    source: str
    cursor: str | None = None
    watermark: datetime | None = None
    content_hash: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class CheckpointStore(Protocol):
    """Anything that can save and load per-source checkpoints."""

    def get(self, source: str) -> Checkpoint | None:
        """Returns the last checkpoint for a source, or None if it never ran."""
        ...

    def put(self, checkpoint: Checkpoint) -> None:
        """Saves the newest checkpoint for a source."""
        ...

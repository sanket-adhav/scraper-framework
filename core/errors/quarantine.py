"""The quarantine (needs-review) sink contract and its record shape (plan2.md §10).

When error policy says QUARANTINE, the runner snapshots what happened here so a
human can inspect and replay it later. File-based implementation lives in
components/; richer tooling arrives in Plans 08–09.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    """A snapshot of one failed scrape: where it failed, why, and with what state."""

    trace_id: str
    stage: str
    error_type: str
    error_message: str
    context_snapshot: Mapping[str, Any]
    quarantined_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class QuarantineSink(Protocol):
    """Anything that can store quarantine records for later human review."""

    def put(self, record: QuarantineRecord) -> None:
        """Stores one quarantine record."""
        ...

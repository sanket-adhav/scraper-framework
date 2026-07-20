"""Checkpoint model — where one source's incremental scraping left off (plan2.md §16)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Where one source's incremental scraping left off."""

    source: str
    cursor: str | None = None
    watermark: datetime | None = None
    content_hash: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

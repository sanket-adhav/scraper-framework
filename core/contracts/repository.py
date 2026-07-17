"""Repository contract — persists Records to any backend (plan2.md §3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.errors.exceptions import ScraperError
from core.models.record import Record


class PersistError(ScraperError):
    """Saving failed. Transient/permanent split lands in Plan 03."""


@runtime_checkable
class Repository(Protocol):
    async def save(self, record: Record) -> None: ...

"""Repository contract — persists Records to any backend (plan2.md §3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.errors.exceptions import PersistError
from core.models.record import Record

__all__ = ["PersistError", "Repository"]


@runtime_checkable
class Repository(Protocol):
    async def save(self, record: Record) -> None: ...

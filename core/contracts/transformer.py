"""Transformer contract — Record in, Record out, pure (plan2.md §3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.errors.exceptions import TransformError
from core.models.record import Record

__all__ = ["TransformError", "Transformer"]


@runtime_checkable
class Transformer(Protocol):
    def transform(self, record: Record) -> Record: ...

"""Transformer contract — Record in, Record out, pure (plan2.md §3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.errors.exceptions import ScraperError
from core.models.record import Record


class TransformError(ScraperError):
    """A transformation could not be applied to the record."""


@runtime_checkable
class Transformer(Protocol):
    def transform(self, record: Record) -> Record: ...

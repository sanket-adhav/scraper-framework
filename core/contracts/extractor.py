"""Extractor contract — turns a Document into a Record via an extraction spec (plan2.md §3, §5)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.contracts.document import Document
from core.errors.exceptions import ExtractionError
from core.models.record import Record

__all__ = ["ExtractionError", "ExtractionSpec", "Extractor"]


@runtime_checkable
class ExtractionSpec(Protocol):
    """Minimal spec surface; the concrete, validated spec model lands with config (Plan 03)."""

    schema_version: str


@runtime_checkable
class Extractor(Protocol):
    def extract(self, doc: Document, spec: ExtractionSpec) -> Record: ...

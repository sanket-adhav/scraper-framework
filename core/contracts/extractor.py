"""Extractor contract — turns a Document into a Record via an extraction spec (plan2.md §3, §5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from core.contracts.document import Document
from core.errors.exceptions import ExtractionError
from core.models.record import Record
from core.models.selector import SelectorKind

__all__ = ["ExtractionError", "ExtractionSpec", "Extractor", "FieldSpec"]


@runtime_checkable
class FieldSpec(Protocol):
    """One field's extraction instructions, as extractors see them. The concrete
    validated model lives in core/config/schema.py (FieldSpecModel)."""

    kind: SelectorKind
    query: str
    required: bool
    cleanup: list[str]
    against: str | None


@runtime_checkable
class ExtractionSpec(Protocol):
    """A whole extraction spec: schema version plus the per-field instructions.
    Satisfied structurally by core.config.schema.ExtractConfigModel."""

    schema_version: str

    @property
    def spec(self) -> Mapping[str, FieldSpec]:
        """The field name → instructions mapping (read-only view)."""
        ...


@runtime_checkable
class Extractor(Protocol):
    def extract(self, doc: Document, spec: ExtractionSpec, *, source_url: str = "") -> Record:
        """Pulls the spec's fields out of the document into a Record. The source
        URL enables `against: url` fields and provenance (ADR 0003)."""
        ...

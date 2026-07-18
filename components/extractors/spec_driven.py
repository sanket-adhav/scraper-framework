"""The generic SpecDrivenExtractor (plan2.md §5) — the piece that makes
"most plugins are just a YAML file" true.

One identical code path for every document format: the spec, not the code,
carries the format knowledge. Required fields that don't match raise
ExtractionError with field detail; optional ones become None and are counted.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from components.extractors.cleanups import apply_chain
from core.contracts.document import Document
from core.contracts.extractor import ExtractionSpec, FieldSpec
from core.errors.exceptions import ExtractionError
from core.models.record import Provenance, Record
from core.models.selector import Selector


class SpecDrivenExtractor:
    """Extracts a Record from any Document by following an extraction spec."""

    def __init__(self, plugin_name: str = "", plugin_version: str = "") -> None:
        """Remembers which plugin owns the specs it runs, and starts the miss counter."""
        self._plugin_name = plugin_name
        self._plugin_version = plugin_version
        self.missing_optional = Counter[str]()  # per-field count of optional misses

    def extract(self, doc: Document, spec: ExtractionSpec, *, source_url: str = "") -> Record:
        """Runs every field's selector (or URL regex), applies its cleanup chain,
        and assembles the Record with schema version and provenance."""
        data: dict[str, Any] = {}
        for name, field in spec.spec.items():
            data[name] = self._extract_field(doc, name, field, source_url)
        return Record(
            data=data,
            schema_version=spec.schema_version,
            provenance=Provenance(
                plugin_name=self._plugin_name,
                plugin_version=self._plugin_version,
                config_fingerprint="",  # stamped by the extract stage, which owns the context
                source_url=source_url,
                scraped_at=datetime.now(UTC),
            ),
        )

    def _extract_field(self, doc: Document, name: str, field: FieldSpec, source_url: str) -> Any:
        """Selects one field's raw value, handles missing per required/optional,
        and runs the cleanup chain."""
        raw: Any
        if field.against == "url":
            raw = _first_group(re.search(field.query, source_url))
        else:
            results = doc.select(Selector(kind=field.kind, query=field.query))
            raw = results[0] if results else None

        if raw is None:
            if field.required:
                raise ExtractionError(
                    f"required field {name!r} matched nothing "
                    f"({field.kind.value}: {field.query!r})",
                    field=name,
                )
            self.missing_optional[name] += 1
            return None
        return apply_chain(raw, field.cleanup, name)


def _first_group(match: re.Match[str] | None) -> str | None:
    """Returns group 1 (or the whole match) of a regex match, or None if it missed."""
    if match is None:
        return None
    return match.group(1) if match.groups() else match.group(0)

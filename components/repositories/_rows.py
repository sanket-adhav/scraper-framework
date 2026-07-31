"""Shared row shape for file repositories: data + schema_version + full provenance."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core.models.record import Record

PROVENANCE_COLUMNS = (
    "schema_version",
    "plugin_name",
    "plugin_version",
    "config_fingerprint",
    "source_url",
    "scraped_at",
)


def record_to_row(record: Record) -> dict[str, Any]:
    """Flattens a Record into one row: its data fields plus the provenance columns."""
    return {
        **dict(record.data),
        "schema_version": record.schema_version,
        "plugin_name": record.provenance.plugin_name,
        "plugin_version": record.provenance.plugin_version,
        "config_fingerprint": record.provenance.config_fingerprint,
        "source_url": record.provenance.source_url,
        "scraped_at": record.provenance.scraped_at.isoformat(),
    }


def row_key(row: dict[str, Any], key_fields: Sequence[str]) -> tuple[Any, ...]:
    """Builds the upsert identity of a row from the configured key fields."""
    return tuple(row.get(f) for f in key_fields)

"""Transformer that maps raw site-specific values onto canonical ones."""

from __future__ import annotations

from collections.abc import Mapping

from components.transformers._shared import with_data
from core.models.record import Record


class EnumMapper:
    """Maps values per field, e.g. {'availability': {'In stock': 'in_stock'}};
    unmapped values pass through unchanged."""

    def __init__(self, mappings: Mapping[str, Mapping[str, str]]) -> None:
        """Remembers the per-field value mappings."""
        self._mappings = {field: dict(values) for field, values in mappings.items()}

    def transform(self, record: Record) -> Record:
        """Replaces each mapped value with its canonical form."""
        data = dict(record.data)
        for field, mapping in self._mappings.items():
            value = data.get(field)
            if isinstance(value, str) and value in mapping:
                data[field] = mapping[value]
        return with_data(record, data)

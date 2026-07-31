"""Transformer that adds constant or copied fields to every record."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from components.transformers._shared import with_data
from core.models.record import Record


class FieldEnricher:
    """Adds config-defined constants (and copies of existing fields) to the record:
    constants: {source: shopverse}; copy: {product_name: title}."""

    def __init__(
        self,
        constants: Mapping[str, Any] | None = None,
        copy: Mapping[str, str] | None = None,
    ) -> None:
        """Remembers the constants to add and the field-copy mapping (new ← existing)."""
        self._constants = dict(constants or {})
        self._copy = dict(copy or {})

    def transform(self, record: Record) -> Record:
        """Adds the constants and copies, never overwriting an existing field."""
        data = dict(record.data)
        for name, value in self._constants.items():
            data.setdefault(name, value)
        for new_name, source_name in self._copy.items():
            if new_name not in data and source_name in data:
                data[new_name] = data[source_name]
        return with_data(record, data)

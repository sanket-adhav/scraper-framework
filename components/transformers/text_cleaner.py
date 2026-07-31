"""Transformer that tidies text fields: trims and collapses whitespace."""

from __future__ import annotations

import re
from collections.abc import Sequence

from components.transformers._shared import with_data
from core.models.record import Record


class TextCleaner:
    """Collapses runs of whitespace and trims the listed fields (or every string field)."""

    def __init__(self, fields: Sequence[str] | None = None) -> None:
        """Remembers which fields to clean; None means every string field."""
        self._fields = list(fields) if fields is not None else None

    def transform(self, record: Record) -> Record:
        """Cleans the chosen text fields, leaving everything else untouched."""
        data = dict(record.data)
        names = self._fields if self._fields is not None else list(data)
        for name in names:
            value = data.get(name)
            if isinstance(value, str):
                data[name] = re.sub(r"\s+", " ", value).strip()
        return with_data(record, data)

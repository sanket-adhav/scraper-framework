"""Transformer that parses dates using EXPLICIT input formats and emits ISO-8601.

DD-MM vs MM-DD ambiguity is resolved by config, never by guessing — an
ambiguous date is only parsed the way the configured formats say.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from components.transformers._shared import with_data
from core.errors.exceptions import TransformError
from core.models.record import Record


class DateNormalizer:
    """Normalizes date fields to ISO-8601 (YYYY-MM-DD) using configured formats, in order."""

    def __init__(self, fields: Sequence[str], input_formats: Sequence[str]) -> None:
        """Remembers the date fields and the strptime formats to try."""
        if not input_formats:
            raise ValueError("date_normalizer needs at least one input format — no guessing")
        self._fields = list(fields)
        self._formats = list(input_formats)

    def transform(self, record: Record) -> Record:
        """Parses each date field with the first matching format; none matching is an error."""
        data = dict(record.data)
        for name in self._fields:
            value = data.get(name)
            if value is None:
                continue
            data[name] = self._parse(name, str(value).strip())
        return with_data(record, data)

    def _parse(self, name: str, text: str) -> str:
        """Tries each configured format and returns the ISO date, or raises clearly."""
        for fmt in self._formats:
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        raise TransformError(
            f"field {name!r}: {text!r} matches none of the configured formats {self._formats}"
        )

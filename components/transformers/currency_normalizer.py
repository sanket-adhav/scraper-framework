"""Transformer that turns messy currency text into plain floats."""

from __future__ import annotations

import re
from collections.abc import Sequence

from components.transformers._shared import with_data
from core.errors.exceptions import TransformError
from core.models.record import Record

_JUNK = re.compile(r"[₹$€£]|(?i:rs\.?|inr|usd|eur|gbp)|,|\s")


class CurrencyNormalizer:
    """Normalizes fields like '₹4,999.00', 'Rs. 4999', 'INR 4,999' to float 4999.0."""

    def __init__(self, fields: Sequence[str]) -> None:
        """Remembers which fields hold currency text."""
        self._fields = list(fields)

    def transform(self, record: Record) -> Record:
        """Converts each currency field to a float; already-numeric values pass through."""
        data = dict(record.data)
        for name in self._fields:
            value = data.get(name)
            if value is None or isinstance(value, int | float):
                continue
            cleaned = _JUNK.sub("", str(value))
            try:
                data[name] = float(cleaned)
            except ValueError as err:
                raise TransformError(f"field {name!r}: cannot normalize {value!r}") from err
        return with_data(record, data)

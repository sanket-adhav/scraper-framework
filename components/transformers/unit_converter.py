"""Transformer that converts numeric fields between units using a fixed factor table."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from components.transformers._shared import with_data
from core.errors.exceptions import TransformError
from core.models.record import Record

_FACTORS: Mapping[tuple[str, str], float] = {
    ("g", "kg"): 0.001,
    ("kg", "g"): 1000.0,
    ("mg", "g"): 0.001,
    ("cm", "m"): 0.01,
    ("m", "cm"): 100.0,
    ("mm", "cm"): 0.1,
    ("ml", "l"): 0.001,
    ("l", "ml"): 1000.0,
}


class UnitConverter:
    """Converts fields like weight-in-grams to kilograms via config:
    conversions: [{field: weight, from: g, to: kg}]."""

    def __init__(self, conversions: Sequence[Mapping[str, Any]]) -> None:
        """Validates and remembers the conversion list."""
        for conv in conversions:
            pair = (conv.get("from"), conv.get("to"))
            if pair not in _FACTORS:
                raise ValueError(f"unsupported conversion {pair}; known: {sorted(_FACTORS)}")
        self._conversions = [dict(c) for c in conversions]

    def transform(self, record: Record) -> Record:
        """Multiplies each configured field by its unit factor."""
        data = dict(record.data)
        for conv in self._conversions:
            name = conv["field"]
            value = data.get(name)
            if value is None:
                continue
            if not isinstance(value, int | float):
                raise TransformError(f"field {name!r}: cannot convert non-number {value!r}")
            data[name] = value * _FACTORS[(conv["from"], conv["to"])]
        return with_data(record, data)

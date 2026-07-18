"""Validator that checks fields hold the configured Python types."""

from __future__ import annotations

from collections.abc import Mapping

from core.contracts.validator import FieldFailure, ValidationResult
from core.models.record import Record

_TYPES: Mapping[str, type | tuple[type, ...]] = {
    "str": str,
    "int": int,
    "float": (int, float),  # an int is an acceptable float
    "bool": bool,
    "list": list,
    "dict": dict,
}


class TypeValidator:
    """Fails any field whose value is not of its configured type (None is skipped —
    that's the required-field validator's job)."""

    def __init__(self, types: Mapping[str, str]) -> None:
        """Remembers the field → type-name mapping (str, int, float, bool, list, dict)."""
        unknown = set(types.values()) - set(_TYPES)
        if unknown:
            raise ValueError(f"unknown type names {sorted(unknown)}; known: {sorted(_TYPES)}")
        self._types = dict(types)

    def validate(self, record: Record) -> ValidationResult:
        """Reports one failure per field holding the wrong type."""
        failures = []
        for name, type_name in self._types.items():
            value = record.data.get(name)
            if value is None:
                continue
            expected = _TYPES[type_name]
            if isinstance(value, bool) and type_name in ("int", "float"):
                failures.append(FieldFailure(name, f"expected {type_name}, got bool"))
            elif not isinstance(value, expected):
                failures.append(
                    FieldFailure(name, f"expected {type_name}, got {type(value).__name__}")
                )
        return ValidationResult(valid=not failures, failures=tuple(failures))

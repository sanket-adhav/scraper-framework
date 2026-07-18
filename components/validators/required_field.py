"""Validator that checks the named fields are present and non-empty."""

from __future__ import annotations

from collections.abc import Sequence

from core.contracts.validator import FieldFailure, ValidationResult
from core.models.record import Record


class RequiredFieldValidator:
    """Fails any listed field whose value is missing, None, or empty text."""

    def __init__(self, fields: Sequence[str]) -> None:
        """Remembers which fields must be present."""
        self._fields = list(fields)

    def validate(self, record: Record) -> ValidationResult:
        """Reports one failure per missing/empty required field."""
        failures = [
            FieldFailure(field=name, message="required field is missing or empty")
            for name in self._fields
            if record.data.get(name) is None or record.data.get(name) == ""
        ]
        return ValidationResult(valid=not failures, failures=tuple(failures))

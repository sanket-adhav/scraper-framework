"""Validator that checks a record against the schema declared for its schema_version."""

from __future__ import annotations

from collections.abc import Mapping

from components.validators.type_validator import TypeValidator
from core.contracts.validator import FieldFailure, ValidationResult
from core.models.record import Record


class SchemaValidator:
    """Looks up the record's schema_version and validates fields against that
    version's field → type mapping; unknown versions fail loudly."""

    def __init__(self, schemas: Mapping[str, Mapping[str, str]]) -> None:
        """Remembers one field-type mapping per schema version."""
        self._validators = {
            version: TypeValidator(fields) for version, fields in schemas.items()
        }

    def validate(self, record: Record) -> ValidationResult:
        """Validates with the right version's schema, or fails if the version is unknown."""
        validator = self._validators.get(record.schema_version)
        if validator is None:
            failure = FieldFailure(
                field="schema_version",
                message=f"no schema defined for version {record.schema_version!r}; "
                f"known: {sorted(self._validators)}",
            )
            return ValidationResult(valid=False, failures=(failure,))
        return validator.validate(record)

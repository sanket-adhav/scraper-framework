"""Validator that flags records already seen, keyed by a hash of chosen fields."""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableSet, Sequence

from core.contracts.validator import FieldFailure, ValidationResult
from core.models.record import Record


class DuplicateDetectorValidator:
    """Fails a record whose key fields hash to something already seen.
    The seen-set is in-memory now and pluggable (Redis backend in Plan 09)."""

    def __init__(self, key_fields: Sequence[str], seen: MutableSet[str] | None = None) -> None:
        """Remembers the key fields and the (injectable) seen-hash store."""
        self._key_fields = list(key_fields)
        self._seen: MutableSet[str] = seen if seen is not None else set()

    def validate(self, record: Record) -> ValidationResult:
        """Hashes the key fields; a repeat is a failure, a first sight is remembered."""
        key = hashlib.sha256(
            json.dumps(
                [record.data.get(f) for f in self._key_fields], sort_keys=True, default=str
            ).encode()
        ).hexdigest()
        if key in self._seen:
            failures = tuple(
                FieldFailure(field=f, message="duplicate record (same key fields already seen)")
                for f in self._key_fields
            )
            return ValidationResult(valid=False, failures=failures)
        self._seen.add(key)
        return ValidationResult(valid=True)

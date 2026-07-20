"""Validator that flags records already seen, keyed by a hash of chosen fields."""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableSet, Sequence

from components.validators.seen_store import InMemorySeenStore, SeenStore
from core.contracts.validator import FieldFailure, ValidationResult
from core.models.record import Record


class DuplicateDetectorValidator:
    """Fails a record whose key fields hash to something already seen.
    The backend is pluggable (in-memory now, Postgres/Redis via SeenStore)."""

    def __init__(
        self,
        key_fields: Sequence[str],
        seen: MutableSet[str] | None = None,
        store: SeenStore | None = None,
    ) -> None:
        """Remembers the key fields and the seen-store backend (in-memory by default).
        The legacy `seen` set is still accepted and wrapped."""
        self._key_fields = list(key_fields)
        if store is not None:
            self._store: SeenStore = store
        elif seen is not None:
            self._store = _SetStore(seen)
        else:
            self._store = InMemorySeenStore()

    def validate(self, record: Record) -> ValidationResult:
        """Hashes the key fields; a repeat is a failure, a first sight is remembered."""
        key = hashlib.sha256(
            json.dumps(
                [record.data.get(f) for f in self._key_fields], sort_keys=True, default=str
            ).encode()
        ).hexdigest()
        if not self._store.check_and_add(key):
            failures = tuple(
                FieldFailure(field=f, message="duplicate record (same key fields already seen)")
                for f in self._key_fields
            )
            return ValidationResult(valid=False, failures=failures)
        return ValidationResult(valid=True)


class _SetStore:
    """Adapts a plain MutableSet to the SeenStore contract (legacy `seen=` support)."""

    def __init__(self, backing: MutableSet[str]) -> None:
        """Wraps an existing set as the seen-store backend."""
        self._backing = backing

    def check_and_add(self, key: str) -> bool:
        """Adds the key to the set, returning whether it was new."""
        if key in self._backing:
            return False
        self._backing.add(key)
        return True

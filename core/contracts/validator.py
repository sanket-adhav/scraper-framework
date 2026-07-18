"""Validator contract — judges a Record, reporting per-field detail (plan2.md §3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.errors.exceptions import ValidationError
from core.models.record import Record

__all__ = ["FieldFailure", "ValidationError", "ValidationResult", "Validator"]


@dataclass(frozen=True, slots=True)
class FieldFailure:
    """One field's validation failure — the granularity per-field metrics depend on."""

    field: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    failures: tuple[FieldFailure, ...] = ()


@runtime_checkable
class Validator(Protocol):
    def validate(self, record: Record) -> ValidationResult: ...

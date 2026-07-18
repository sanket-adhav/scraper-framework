"""Validator for config-expressed business rules like 'price > 0'."""

from __future__ import annotations

import operator
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from core.contracts.validator import FieldFailure, ValidationResult
from core.models.record import Record

_OPS: Mapping[str, Callable[[Any, Any], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


class BusinessRuleValidator:
    """Checks structured rules from config: [{field, op, value}, ...].
    Structured on purpose — no expression parsing, no eval, no DSL creep."""

    def __init__(self, rules: Sequence[Mapping[str, Any]]) -> None:
        """Validates and remembers the rule list."""
        for rule in rules:
            if rule.get("op") not in _OPS:
                raise ValueError(f"unknown op {rule.get('op')!r}; known: {sorted(_OPS)}")
            if "field" not in rule or "value" not in rule:
                raise ValueError(f"rule needs field/op/value, got {dict(rule)}")
        self._rules = [dict(r) for r in rules]

    def validate(self, record: Record) -> ValidationResult:
        """Reports one failure per rule the record breaks (None values are skipped)."""
        failures = []
        for rule in self._rules:
            value = record.data.get(rule["field"])
            if value is None:
                continue
            try:
                ok = _OPS[rule["op"]](value, rule["value"])
            except TypeError:
                ok = False
            if not ok:
                failures.append(
                    FieldFailure(
                        field=rule["field"],
                        message=f"rule failed: {rule['field']} {rule['op']} {rule['value']!r} "
                        f"(value: {value!r})",
                    )
                )
        return ValidationResult(valid=not failures, failures=tuple(failures))

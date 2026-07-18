"""The validate pipeline stage: runs every validator and fails with per-field detail."""

from __future__ import annotations

from collections.abc import Sequence

from core.contracts.stage import Context, ErrorAction
from core.contracts.validator import FieldFailure, ValidationResult, Validator
from core.errors.exceptions import ScraperError, ValidationError


class ValidateStage:
    """Pipeline stage that judges ctx.record with all configured validators."""

    name = "validate"

    def __init__(self, validators: Sequence[Validator]) -> None:
        """Remembers the validators to run, in order."""
        self._validators = list(validators)

    async def run(self, ctx: Context) -> Context:
        """Collects every validator's failures; any failure stops the record here."""
        if ctx.record is None:
            raise ValidationError("validate stage needs ctx.record, but none was set")
        failures: list[FieldFailure] = []
        for validator in self._validators:
            failures.extend(validator.validate(ctx.record).failures)
        ctx.validation_result = ValidationResult(valid=not failures, failures=tuple(failures))
        if failures:
            detail = "; ".join(f"{f.field}: {f.message}" for f in failures)
            raise ValidationError(f"record failed validation — {detail}")
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Fallback when config is silent: invalid records go to review, never to storage."""
        return ErrorAction.QUARANTINE

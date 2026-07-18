"""The transform pipeline stage: runs the configured transformers over ctx.record, in order."""

from __future__ import annotations

from collections.abc import Sequence

from core.contracts.stage import Context, ErrorAction
from core.contracts.transformer import Transformer
from core.errors.exceptions import ScraperError, TransformError


class TransformStage:
    """Pipeline stage that pipes the record through each transformer in sequence."""

    name = "transform"

    def __init__(self, transformers: Sequence[Transformer]) -> None:
        """Remembers the transformers to apply, in order."""
        self._transformers = list(transformers)

    async def run(self, ctx: Context) -> Context:
        """Applies every transformer; each returns a new immutable record."""
        if ctx.record is None:
            raise TransformError("transform stage needs ctx.record, but none was set")
        record = ctx.record
        for transformer in self._transformers:
            record = transformer.transform(record)
        ctx.record = record
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Fallback when config is silent: a value we can't normalize goes to review."""
        return ErrorAction.QUARANTINE

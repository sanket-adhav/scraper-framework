"""The extract pipeline stage: runs the extractor over ctx.document and stamps provenance."""
# extract records from the document
from __future__ import annotations

from dataclasses import replace

from core.contracts.extractor import ExtractionSpec, Extractor
from core.contracts.stage import Context, ErrorAction
from core.errors.exceptions import ExtractionError, ScraperError


class ExtractStage:
    """Pipeline stage that extracts a Record from the document using the spec."""

    name = "extract"

    def __init__(self, extractor: Extractor, spec: ExtractionSpec) -> None:
        """Remembers the extractor implementation and the (already validated) spec."""
        self._extractor = extractor
        self._spec = spec

    async def run(self, ctx: Context) -> Context:
        """Extracts the record, then stamps the config fingerprint into its provenance
        (the fingerprint belongs to the context, not to extraction logic)."""
        if ctx.document is None:
            raise ExtractionError("extract stage needs ctx.document, but none was set")
        source_url = ctx.request.url if ctx.request else ""
        record = self._extractor.extract(ctx.document, self._spec, source_url=source_url)
        ctx.record = replace(
            record,
            provenance=replace(record.provenance, config_fingerprint=ctx.config_fingerprint),
        )
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Fallback when config is silent: spec/page drift goes to review, not silence."""
        return ErrorAction.QUARANTINE

"""The parse pipeline stage: turns ctx.response into ctx.document via the configured parser."""
# parses the document
from __future__ import annotations

from core.contracts.parser import Parser
from core.contracts.stage import Context, ErrorAction
from core.errors.exceptions import ParseError, ScraperError


class ParseStage:
    """Pipeline stage that parses the fetched response into a queryable Document."""

    name = "parse"

    def __init__(self, parser: Parser) -> None:
        """Remembers which parser this pipeline uses (declared in config)."""
        self._parser = parser

    async def run(self, ctx: Context) -> Context:
        """Parses ctx.response and stores the resulting document on the context."""
        if ctx.response is None:
            raise ParseError("parse stage needs ctx.response, but none was set")
        ctx.document = self._parser.parse(ctx.response)
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Fallback when config is silent: a page we can't parse goes to review."""
        return ErrorAction.QUARANTINE

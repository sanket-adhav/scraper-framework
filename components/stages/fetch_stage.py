"""The fetch pipeline stage: runs the middleware-wrapped fetcher and stores the Response."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from core.contracts.fetcher import Fetcher
from core.contracts.middleware import Middleware
from core.contracts.stage import Context, ErrorAction
from core.errors.exceptions import FetchError, ScraperError
from core.middleware_runner import compose


class FetchStage:
    """Pipeline stage that fetches ctx.request through the middleware stack."""

    name = "fetch"

    def __init__(self, fetcher: Fetcher, middlewares: Sequence[Middleware] = ()) -> None:
        """Composes the middleware onion around the given fetcher, once."""
        self._entry = compose(list(middlewares), fetcher.fetch)

    async def run(self, ctx: Context) -> Context:
        """Fetches the request, tagged with the trace id and plugin name so
        middleware (observability, cost tracking) can attribute it."""
        if ctx.request is None:
            raise FetchError("fetch stage needs ctx.request, but none was set")
        request = ctx.request
        plugin = (ctx.config.get("plugin") or {}).get("name", "-")
        tagged = replace(
            request,
            metadata={**request.metadata, "trace_id": ctx.trace_id, "plugin": plugin},
        )
        ctx.response = await self._entry(tagged)
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Fallback when config is silent: retry transient fetch errors, abort the rest."""
        if isinstance(err, FetchError) and err.transient:
            return ErrorAction.RETRY
        return ErrorAction.ABORT

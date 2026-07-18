"""The one middleware composer (plan2.md §6, §8).

Composes an ordered list of Middleware into a single `Next` callable around the
fetch. First in the list = outermost layer. This is the ONLY wrapping mechanism
in the codebase — anything proposed as a "preprocessor chain", "fetch hook", or
decorator is, by design rule, a middleware in this stack.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.contracts.middleware import Middleware, Next
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


def compose(middlewares: Sequence[Middleware], fetch: Next) -> Next:
    """Wraps the fetch callable in the middleware onion and returns the entry point."""
    wrapped = fetch
    for middleware in reversed(middlewares):
        wrapped = _bind(middleware, wrapped)
    return wrapped


def _bind(middleware: Middleware, inner: Next) -> Next:
    """Fixes one middleware around its inner neighbor as a plain callable."""

    async def call(request: ScrapeRequest) -> Response:
        """Passes the request into this middleware layer."""
        return await middleware(request, inner)

    return call

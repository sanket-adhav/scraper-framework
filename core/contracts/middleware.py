"""Middleware contract — THE one wrapping mechanism for cross-cutting concerns (plan2.md §6).

Onion model, identical to ASGI middleware: inspect/modify the request, call
`next`, inspect/modify the response, short-circuit, or retry. Every cross-cutting
concern (rate limit, retry, proxy, auth, cache, circuit breaker, block detection,
observability) is one of these — there is no other hook, chain, or decorator.

Middleware sees ScrapeRequest/Response only — never the pipeline Context.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

Next = Callable[[ScrapeRequest], Awaitable[Response]]


@runtime_checkable
class Middleware(Protocol):
    async def __call__(self, request: ScrapeRequest, next: Next) -> Response: ...

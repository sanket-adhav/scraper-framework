"""Proxy-rotation middleware (plan2.md §6, §12, Plan 07).

Picks a proxy per request from a pool and attaches it to the request metadata
(the fetcher reads it). On a block signal, the proxy that was used is put on
cooldown so we stop routing through a burned exit. Pool providers are pluggable;
a static list is the Phase-2 default.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from core.contracts.middleware import Next
from core.errors.exceptions import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

TimeFn = Callable[[], float]


class _Proxy:
    """One proxy URL plus the time it becomes usable again after a cooldown."""

    def __init__(self, url: str) -> None:
        """Starts available immediately."""
        self.url = url
        self.available_at = 0.0


class ProxyRotationMiddleware:
    """Middleware that routes each request through a healthy proxy, cooling down burned ones."""

    def __init__(
        self,
        proxies: Sequence[str],
        cooldown_s: float = 120.0,
        time_fn: TimeFn = time.monotonic,
    ) -> None:
        """Stores the proxy pool and how long a blocked proxy sits out."""
        if not proxies:
            raise ValueError("proxy_rotation needs at least one proxy")
        self._proxies = [_Proxy(url) for url in proxies]
        self._cooldown_s = cooldown_s
        self._time = time_fn
        self._next = 0

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Attaches a healthy proxy; on a block, cools that proxy down and re-raises."""
        proxy = self._pick()
        if proxy is None:
            raise FetchError("all proxies are on cooldown", transient=True)
        tagged = _with_proxy(request, proxy.url)
        try:
            return await next(tagged)
        except FetchError as err:
            if err.blocked:
                proxy.available_at = self._time() + self._cooldown_s
            raise

    def _pick(self) -> _Proxy | None:
        """Round-robins to the next proxy that isn't on cooldown."""
        now = self._time()
        for _ in range(len(self._proxies)):
            proxy = self._proxies[self._next % len(self._proxies)]
            self._next += 1
            if proxy.available_at <= now:
                return proxy
        return None


def _with_proxy(request: ScrapeRequest, proxy_url: str) -> ScrapeRequest:
    """Returns a copy of the request carrying the chosen proxy in its metadata."""
    from dataclasses import replace

    return replace(request, metadata={**request.metadata, "proxy": proxy_url})

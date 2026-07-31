"""Rate-limit middleware: a token bucket per target domain (plan2.md §6).

Every call — first attempt or retry — must take a token before the fetch runs,
which is what makes retry storms impossible when retry wraps this middleware.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from core.contracts.middleware import Next
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

TimeFn = Callable[[], float]
SleepFn = Callable[[float], Awaitable[None]]


class _TokenBucket:
    """One domain's budget: refills at `rate` tokens/second up to `burst` capacity."""

    def __init__(self, rate: float, burst: float, time_fn: TimeFn, sleep_fn: SleepFn) -> None:
        """Starts full so the first requests up to the burst size go straight through."""
        self._rate = rate
        self._burst = burst
        self._tokens = burst
        self._time = time_fn
        self._sleep = sleep_fn
        self._last = time_fn()
        self.acquired_count = 0  # visible to tests: every fetch attempt shows up here

    async def acquire(self) -> None:
        """Takes one token, waiting for the refill if the bucket is empty."""
        while True:
            now = self._time()
            self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
            self._last = now
            if self._tokens >= 1:
                self._tokens -= 1
                self.acquired_count += 1
                return
            await self._sleep((1 - self._tokens) / self._rate)


class RateLimiterMiddleware:
    """Middleware that makes every request wait for its domain's token bucket."""

    def __init__(
        self,
        rate: float = 1.0,
        burst: float = 1.0,
        domains: Mapping[str, Mapping[str, float]] | None = None,
        time_fn: TimeFn = time.monotonic,
        sleep_fn: SleepFn | None = None,
    ) -> None:
        """Stores the default budget, per-domain overrides, and injectable clocks (for tests)."""
        self._rate = rate
        self._burst = burst
        self._overrides = dict(domains or {})
        self._time = time_fn
        self._sleep: SleepFn = sleep_fn if sleep_fn is not None else _asyncio_sleep
        self._buckets: dict[str, _TokenBucket] = {}

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Waits for a token for this request's domain, then lets the fetch proceed."""
        await self.bucket_for(urlsplit(request.url).netloc).acquire()
        return await next(request)

    def bucket_for(self, domain: str) -> _TokenBucket:
        """Returns (creating on first use) the token bucket for one domain."""
        if domain not in self._buckets:
            override: Mapping[str, Any] = self._overrides.get(domain, {})
            self._buckets[domain] = _TokenBucket(
                rate=float(override.get("rate", self._rate)),
                burst=float(override.get("burst", self._burst)),
                time_fn=self._time,
                sleep_fn=self._sleep,
            )
        return self._buckets[domain]


async def _asyncio_sleep(seconds: float) -> None:
    """Default sleep — real asyncio sleeping outside tests."""
    await asyncio.sleep(seconds)

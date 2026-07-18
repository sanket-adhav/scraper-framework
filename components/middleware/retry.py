"""Retry middleware: exponential backoff + jitter for transient failures (plan2.md §6).

Retries only FetchError(transient=True) and throttle statuses (429/503,
honoring Retry-After). Each retry re-enters the inner stack, so rate limiting
still applies to every attempt. Permanent errors are never retried.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence

from core.contracts.middleware import Next
from core.errors.exceptions import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

SleepFn = Callable[[float], Awaitable[None]]
RandomFn = Callable[[], float]


class RetryMiddleware:
    """Middleware that re-tries transient fetch failures with growing, jittered delays."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_s: float = 0.5,
        max_delay_s: float = 30.0,
        jitter: float = 0.1,
        retry_statuses: Sequence[int] = (429, 503),
        sleep_fn: SleepFn | None = None,
        random_fn: RandomFn = random.random,
    ) -> None:
        """Stores the retry budget, backoff shape, and injectable sleep/random (for tests)."""
        self._max_attempts = max(1, max_attempts)
        self._base_delay_s = base_delay_s
        self._max_delay_s = max_delay_s
        self._jitter = jitter
        self._retry_statuses = frozenset(retry_statuses)
        self._sleep: SleepFn = sleep_fn if sleep_fn is not None else _asyncio_sleep
        self._random = random_fn

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Tries the fetch, retrying transient errors and throttle statuses within budget."""
        attempt = 0
        while True:
            try:
                response = await next(request.with_attempt(attempt))
            except FetchError as err:
                if not err.transient or attempt >= self._max_attempts - 1:
                    raise
                await self._sleep(self._backoff(attempt))
            else:
                if response.status in self._retry_statuses and attempt < self._max_attempts - 1:
                    await self._sleep(self._retry_after(response) or self._backoff(attempt))
                else:
                    return response
            attempt += 1

    def _backoff(self, attempt: int) -> float:
        """Returns the exponential delay for this attempt, capped, plus jitter."""
        delay: float = min(self._base_delay_s * (2**attempt), self._max_delay_s)
        jittered: float = delay + delay * self._jitter * self._random()
        return jittered

    def _retry_after(self, response: Response) -> float | None:
        """Reads the server's Retry-After header (in seconds) if it sent one."""
        raw = response.headers.get("retry-after") or response.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return min(float(raw), self._max_delay_s)
        except ValueError:
            return None


async def _asyncio_sleep(seconds: float) -> None:
    """Default sleep — real asyncio sleeping outside tests."""
    await asyncio.sleep(seconds)

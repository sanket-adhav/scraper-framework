"""Response-cache middleware (plan2.md §6, Plan 07).

Serves a recent response for the same request without fetching, keyed on a hash
of method+url. NEVER caches blocked or error responses — only real content, so a
cache can't pin a CAPTCHA page in place.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass

from core.contracts.middleware import Next
from core.errors.exceptions import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

TimeFn = Callable[[], float]


@dataclass(slots=True)
class _Entry:
    """One cached response and the time it was stored."""

    response: Response
    stored_at: float


class CachingMiddleware:
    """Middleware that reuses recent good responses instead of re-fetching."""

    def __init__(
        self, ttl_s: float = 300.0, max_status: int = 400, time_fn: TimeFn = time.monotonic
    ) -> None:
        """Stores the cache lifetime and the status cutoff above which nothing is cached."""
        self._ttl_s = ttl_s
        self._max_status = max_status
        self._time = time_fn
        self._store: dict[str, _Entry] = {}
        self.hits = 0
        self.misses = 0

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Returns a fresh cached response if present; otherwise fetches and maybe caches it."""
        key = self._key(request)
        entry = self._store.get(key)
        if entry is not None and (self._time() - entry.stored_at) < self._ttl_s:
            self.hits += 1
            return entry.response
        self.misses += 1
        try:
            response = await next(request)
        except FetchError:
            raise  # never cache failures (including blocks)
        if response.status < self._max_status:
            self._store[key] = _Entry(response=response, stored_at=self._time())
        return response

    @staticmethod
    def _key(request: ScrapeRequest) -> str:
        """Builds the cache key from the request method and URL."""
        return hashlib.sha256(f"{request.method} {request.url}".encode()).hexdigest()

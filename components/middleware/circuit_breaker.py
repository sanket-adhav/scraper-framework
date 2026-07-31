"""Circuit-breaker middleware (plan2.md §6, Plan 07).

Per target domain, opens after too many failures/blocks so we stop hammering a
site that's down or blocking us. While open, requests fail fast; after a cooldown
it goes half-open and lets one probe through before closing or re-opening.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from urllib.parse import urlsplit

from core.contracts.middleware import Next
from core.errors.exceptions import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

TimeFn = Callable[[], float]


class CircuitState(StrEnum):
    """The three states of one domain's breaker."""

    CLOSED = "closed"  # normal — requests flow
    OPEN = "open"  # tripped — fail fast, don't touch the site
    HALF_OPEN = "half_open"  # cooldown elapsed — allow one probe


class OpenCircuitError(FetchError):
    """The breaker for this domain is open, so the request failed without a fetch."""

    def __init__(self, domain: str) -> None:
        """Builds a permanent, non-blocked fetch error naming the tripped domain."""
        super().__init__(f"circuit open for {domain}", transient=False)


class _Breaker:
    """One domain's failure count, state, and the time it may next probe."""

    def __init__(self) -> None:
        """Starts closed with no failures."""
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at = 0.0


class CircuitBreakerMiddleware:
    """Middleware that trips per-domain to stop hammering failing or blocking sites."""

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_s: float = 30.0,
        time_fn: TimeFn = time.monotonic,
    ) -> None:
        """Stores how many failures trip the breaker and how long it stays open."""
        self._threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._time = time_fn
        self._breakers: dict[str, _Breaker] = {}

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Fails fast if the domain's breaker is open; otherwise records the outcome."""
        domain = urlsplit(request.url).netloc
        breaker = self._breakers.setdefault(domain, _Breaker())
        if breaker.state is CircuitState.OPEN:
            if self._time() - breaker.opened_at < self._cooldown_s:
                raise OpenCircuitError(domain)
            breaker.state = CircuitState.HALF_OPEN
        try:
            response = await next(request)
        except FetchError as err:
            self._record_failure(breaker)
            raise err
        if response.status >= 500:
            self._record_failure(breaker)
        else:
            self._record_success(breaker)
        return response

    def state_for(self, domain: str) -> CircuitState:
        """Returns the current breaker state for a domain (for tests/metrics)."""
        return self._breakers.setdefault(domain, _Breaker()).state

    def _record_failure(self, breaker: _Breaker) -> None:
        """Counts a failure; trips the breaker open once the threshold is reached."""
        breaker.failures += 1
        if breaker.failures >= self._threshold or breaker.state is CircuitState.HALF_OPEN:
            breaker.state = CircuitState.OPEN
            breaker.opened_at = self._time()

    def _record_success(self, breaker: _Breaker) -> None:
        """Clears the failure count and closes the breaker."""
        breaker.failures = 0
        breaker.state = CircuitState.CLOSED

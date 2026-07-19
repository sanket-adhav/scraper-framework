"""Cost-tracking middleware (plan2.md §14, Plan 07).

Counts the things that cost money per plugin — fetch counts, bytes downloaded,
and browser-minutes when a browser fetcher ran — so the monthly cost review
(Plan 10) has real data from the very first Playwright fetch, not a retrofit.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from core.contracts.middleware import Next
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

TimeFn = Callable[[], float]


@dataclass(slots=True)
class CostCounters:
    """Running totals of the cost-relevant quantities for one plugin."""

    fetches: int = 0
    bytes_downloaded: int = 0
    browser_seconds: float = 0.0
    errors: int = 0


class CostTrackerMiddleware:
    """Middleware that tallies per-plugin fetch counts, bytes, and browser time."""

    def __init__(self, browser: bool = False, time_fn: TimeFn = time.monotonic) -> None:
        """`browser=True` marks this stack as browser-based so time counts as browser-minutes."""
        self._browser = browser
        self._time = time_fn
        self.by_plugin: dict[str, CostCounters] = {}

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Times the fetch and updates the counters for the request's plugin."""
        plugin = str(request.metadata.get("plugin", "-"))
        counters = self.by_plugin.setdefault(plugin, CostCounters())
        started = self._time()
        try:
            response = await next(request)
        except Exception:
            counters.errors += 1
            raise
        finally:
            if self._browser:
                counters.browser_seconds += self._time() - started
        counters.fetches += 1
        counters.bytes_downloaded += len(response.body)
        return response

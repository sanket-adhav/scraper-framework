"""Observability middleware: one structured log line per actual fetch attempt,
with the trace id carried through (plan2.md §10)."""

from __future__ import annotations

import logging
import time

from core.contracts.middleware import Next
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


class ObservabilityMiddleware:
    """Middleware that times each fetch attempt and logs its outcome with the trace id."""

    def __init__(self, logger_name: str = "scraper.fetch") -> None:
        """Uses (or creates) the named logger for the structured fetch log."""
        self._logger = logging.getLogger(logger_name)

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Runs the fetch, then logs url, status, attempt, timing, and trace id."""
        trace_id = str(request.metadata.get("trace_id", "-"))
        started = time.monotonic()
        try:
            response = await next(request)
        except Exception as err:
            self._logger.warning(
                "fetch failed",
                extra={
                    "trace_id": trace_id,
                    "url": request.url,
                    "attempt": request.attempt,
                    "elapsed_ms": (time.monotonic() - started) * 1000,
                    "error": repr(err),
                },
            )
            raise
        self._logger.info(
            "fetch ok",
            extra={
                "trace_id": trace_id,
                "url": request.url,
                "attempt": request.attempt,
                "status": response.status,
                "elapsed_ms": (time.monotonic() - started) * 1000,
            },
        )
        return response

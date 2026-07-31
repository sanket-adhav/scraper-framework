"""Fake stages and helpers used by pipeline/engine/config tests."""

from __future__ import annotations

import asyncio

from core.contracts.stage import Context, ErrorAction
from core.errors.exceptions import ScraperError
from core.models.scrape_request import ScrapeRequest


class FakeStage:
    """A controllable stage: records when it runs, and can fail on demand."""

    def __init__(
        self,
        name: str,
        log: list[str],
        *,
        fail_times: int = 0,
        error: ScraperError | None = None,
        on_error_action: ErrorAction = ErrorAction.ABORT,
        sleep_s: float = 0.0,
    ) -> None:
        """Sets up the stage's name, shared run log, and failure behavior."""
        self.name = name
        self._log = log
        self._fail_remaining = fail_times
        self._error = error or ScraperError(f"{name} failed")
        self._on_error_action = on_error_action
        self._sleep_s = sleep_s

    async def run(self, ctx: Context) -> Context:
        """Logs the run, then fails or sleeps if configured to."""
        self._log.append(self.name)
        if self._sleep_s:
            await asyncio.sleep(self._sleep_s)
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise self._error
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Returns this stage's configured fallback action."""
        return self._on_error_action


class DiscoverStage:
    """A fake discover stage: first-page requests spawn the given child URLs."""

    name = "discover"

    def __init__(self, child_urls: list[str]) -> None:
        """Remembers which child URLs to emit for page-1 requests."""
        self._child_urls = child_urls

    async def run(self, ctx: Context) -> Context:
        """Appends child requests unless this request is itself a child."""
        assert ctx.request is not None
        if not ctx.request.metadata.get("is_child"):
            ctx.discovered_requests.extend(
                ScrapeRequest(url=url, metadata={"is_child": True}) for url in self._child_urls
            )
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Discover failures abort by default."""
        return ErrorAction.ABORT

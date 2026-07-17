"""Fetcher contract — turns a ScrapeRequest into a Response over any transport (plan2.md §3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.errors.exceptions import ScraperError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


class FetchError(ScraperError):
    """Fetch failed. Transient/permanent split and block signaling land in Plan 03/04."""


@runtime_checkable
class Fetcher(Protocol):
    async def fetch(self, request: ScrapeRequest) -> Response: ...

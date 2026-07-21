"""The discover pipeline stage: finds follow-up requests (pagination, crawling)
in the current document and hands them back to the engine (plan2.md §4).

Pagination is data flowing through the pipeline — never a method to override.
A page that yields no match simply ends the chain.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.contracts.stage import Context, ErrorAction
from core.errors.exceptions import ScraperError
from core.models.scrape_request import ScrapeRequest
from core.models.selector import Selector, SelectorKind


class DiscoverStage:
    """Pipeline stage that selects next-page URLs (or cursor values) from the document."""

    name = "discover"

    def __init__(
        self,
        next_url: Mapping[str, Any],
        url_template: str | None = None,
        max_new: int = 100,
    ) -> None:
        """Remembers the selector that finds the next page, an optional URL template
        ({value} is replaced by the selected text), and a per-page safety cap."""
        self._selector = Selector(
            kind=SelectorKind(next_url["kind"]), query=str(next_url["query"])
        )
        self._url_template = url_template
        self._max_new = max_new

    async def run(self, ctx: Context) -> Context:
        """Appends one request per selected value; no matches means the chain ends here."""
        if ctx.document is None:
            raise ScraperError("discover stage needs ctx.document, but none was set")
        for value in ctx.document.select(self._selector)[: self._max_new]:
            text = str(value).strip()
            if not text:
                continue
            url = self._url_template.format(value=text) if self._url_template else text
            origin = ctx.request.url if ctx.request else ""
            from urllib.parse import urljoin
            if origin and not url.startswith(("http://", "https://")):
                url = urljoin(origin, url)
            ctx.discovered_requests.append(
                ScrapeRequest(url=url, metadata={"discovered_from": origin})
            )
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Fallback when config is silent: failed discovery skips (the page itself
        still yields its record); the chain just stops growing."""
        return ErrorAction.SKIP

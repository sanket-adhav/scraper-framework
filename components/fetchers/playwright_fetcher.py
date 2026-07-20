"""Browser fetcher backed by Playwright for JS-heavy pages (plan2.md §12, Plan 07).

Browser contexts are the expensive resource, so they are pooled and recycled
after N uses. The browser is injectable (a factory), which keeps the whole test
suite browser-free — a real Chromium is used only in the opt-in e2e test.

Produces the SAME Response model as HttpFetcher, so downstream stages cannot
tell which fetcher ran (proven by the shared fetcher contract suite).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from core.errors.exceptions import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

BrowserFactory = Callable[[], Awaitable[Any]]


async def _launch_chromium() -> Any:
    """Launches a headless Chromium via Playwright (needs `playwright install chromium`)."""
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    browser._sf_playwright = playwright  # type: ignore[attr-defined]  # keep driver alive
    return browser


class PlaywrightFetcher:
    """Fetches pages with a real browser, reusing a small pool of browser contexts."""

    def __init__(
        self,
        *,
        browser_factory: BrowserFactory | None = None,
        context_pool_size: int = 2,
        recycle_after: int = 20,
        timeout_s: float = 30.0,
        wait_until: str = "load",
        viewport: Mapping[str, int] | None = None,
        locale: str = "en-US",
        timezone: str | None = None,
        user_agent: str | None = None,
        java_script_enabled: bool = True,
    ) -> None:
        """Stores browser settings and fingerprint knobs (viewport, locale, UA, etc.)."""
        self._browser_factory = browser_factory or _launch_chromium
        self._pool_size = max(1, context_pool_size)
        self._recycle_after = max(1, recycle_after)
        self._timeout_ms = timeout_s * 1000
        self._wait_until = wait_until
        self._context_options: dict[str, Any] = {
            "locale": locale,
            "java_script_enabled": java_script_enabled,
        }
        if viewport is not None:
            self._context_options["viewport"] = dict(viewport)
        if timezone is not None:
            self._context_options["timezone_id"] = timezone
        if user_agent is not None:
            self._context_options["user_agent"] = user_agent
        self._browser: Any = None
        self._pool: list[_PooledContext] = []
        self._lock = asyncio.Lock()

    async def fetch(self, request: ScrapeRequest) -> Response:
        """Opens a page in a pooled context, navigates, and returns the rendered HTML.
        If the target URL is a PDF or uploads path, bypasses browser navigation and
        fetches it directly using httpx to prevent browser download timeouts."""
        started = time.monotonic()

        # Intercept direct binary/PDF files to fetch them efficiently via HTTP
        url_lower = request.url.lower()
        if url_lower.split("?")[0].endswith(".pdf") or "/uploads/" in url_lower:
            import httpx

            try:
                headers = dict(request.headers)
                # Ensure the User-Agent is passed
                if "User-Agent" not in headers and self._context_options.get("user_agent"):
                    headers["User-Agent"] = self._context_options["user_agent"]

                async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                    reply = await client.get(
                        request.url, headers=headers, cookies=dict(request.cookies)
                    )
                    content_type = reply.headers.get("content-type", "application/pdf")
                    ct = content_type.split(";")[0].strip() if content_type else "application/pdf"
                    return Response(
                        status=reply.status_code,
                        headers=dict(reply.headers),
                        body=reply.content,
                        elapsed_ms=(time.monotonic() - started) * 1000,
                        content_type=ct,
                    )
            except Exception as err:
                raise FetchError(
                    f"{request.url}: direct HTTP download of binary URL failed: {err!r}",
                    transient=True,
                ) from err

        pooled = await self._acquire_context(request)
        page = await pooled.context.new_page()
        try:
            reply = await page.goto(
                request.url, wait_until=self._wait_until, timeout=self._timeout_ms
            )
            body = (await page.content()).encode("utf-8")
            status = reply.status if reply is not None else 200
            headers = dict(reply.headers) if reply is not None else {}
        except Exception as err:  # noqa: BLE001 — normalize every browser error to a typed one
            raise FetchError(
                f"{request.url}: browser fetch failed: {err!r}", transient=True
            ) from err
        finally:
            await page.close()
            await self._release_context(pooled)
        content_type = headers.get("content-type", "text/html")
        return Response(
            status=status,
            headers=headers,
            body=body,
            elapsed_ms=(time.monotonic() - started) * 1000,
            content_type=content_type.split(";")[0].strip() if content_type else "text/html",
        )

    async def _acquire_context(self, request: ScrapeRequest) -> _PooledContext:
        """Reuses a pooled context or creates one; a per-request proxy forces a fresh context."""
        proxy = request.metadata.get("proxy")
        async with self._lock:
            if self._browser is None:
                self._browser = await self._browser_factory()
            if proxy is None:
                for pooled in self._pool:
                    if not pooled.in_use:
                        pooled.in_use = True
                        return pooled
            options = dict(self._context_options)
            if proxy is not None:
                options["proxy"] = {"server": str(proxy)}
            context = await self._browser.new_context(**options)
            pooled = _PooledContext(context=context, in_use=True, ephemeral=proxy is not None)
            if not pooled.ephemeral and len(self._pool) < self._pool_size:
                self._pool.append(pooled)
            return pooled

    async def _release_context(self, pooled: _PooledContext) -> None:
        """Frees the context back to the pool, recycling it once it's well-used."""
        pooled.uses += 1
        async with self._lock:
            if pooled.ephemeral or pooled.uses >= self._recycle_after:
                if pooled in self._pool:
                    self._pool.remove(pooled)
                await pooled.context.close()
            else:
                pooled.in_use = False

    async def aclose(self) -> None:
        """Closes every pooled context and the browser."""
        for pooled in list(self._pool):
            await pooled.context.close()
        self._pool.clear()
        if self._browser is not None:
            await self._browser.close()
            playwright = getattr(self._browser, "_sf_playwright", None)
            if playwright is not None:
                await playwright.stop()
            self._browser = None


class _PooledContext:
    """A browser context plus its pool bookkeeping (in-use flag, use count)."""

    __slots__ = ("context", "in_use", "uses", "ephemeral")

    def __init__(self, context: Any, in_use: bool, ephemeral: bool = False) -> None:
        """Wraps a browser context with usage tracking."""
        self.context = context
        self.in_use = in_use
        self.uses = 0
        self.ephemeral = ephemeral

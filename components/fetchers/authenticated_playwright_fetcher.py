"""Playwright fetcher for sites that sit behind a login form and paginate in-page.

Two things the stock PlaywrightFetcher cannot do, both needed by AMS-style apps:

1. **Form login.** The session is established once against a login URL and then
   reused for every request in the run, so protected pages return content rather
   than a redirect to the login screen.
2. **In-page pagination.** Grids (FluentUI, Syncfusion, AG Grid, ...) page on the
   client without changing the URL. When `paginate_next_selector` is set the
   fetcher clicks through every page and splices the extra rows into the first
   page's table, so downstream stages see one document holding the whole grid.

Credentials never appear in config as plaintext: `username`/`password` take
`secret://env/NAME` references, which the config loader resolves at
component-build time (the config fingerprint never sees the secret).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.contracts.fetcher import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


class AuthenticatedPlaywrightFetcher:
    """Renders pages in a logged-in browser session, optionally merging paged grid rows."""

    def __init__(
        self,
        *,
        login_url: str = "",
        username: str = "",
        password: str = "",
        username_selector: str = 'input[name="Input.Email"]',
        password_selector: str = 'input[name="Input.Password"]',
        submit_selector: str = 'button[type="submit"]',
        logged_out_selector: str = 'input[name="Input.Password"]',
        timeout_s: float = 45.0,
        wait_until: str = "networkidle",
        wait_after_s: float = 3.0,
        wait_selector: str | None = None,
        paginate_next_selector: str | None = None,
        paginate_row_container: str = "table tbody",
        paginate_row_selector: str = "tr",
        paginate_max_pages: int = 25,
        headless: bool = True,
        viewport_width: int = 1600,
        viewport_height: int = 1200,
        user_agent: str | None = None,
    ) -> None:
        """Stores login, wait, and pagination settings; the browser starts lazily."""
        self._login_url = login_url
        self._username = username
        self._password = password
        self._username_selector = username_selector
        self._password_selector = password_selector
        self._submit_selector = submit_selector
        self._logged_out_selector = logged_out_selector
        self._timeout_ms = int(timeout_s * 1000)
        self._wait_until = wait_until
        self._wait_after_s = wait_after_s
        self._wait_selector = wait_selector
        self._paginate_next_selector = paginate_next_selector
        self._paginate_row_container = paginate_row_container
        self._paginate_row_selector = paginate_row_selector
        self._paginate_max_pages = paginate_max_pages
        self._headless = headless
        self._viewport = {"width": viewport_width, "height": viewport_height}
        self._user_agent = user_agent

        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._lock = asyncio.Lock()

    # -- session ---------------------------------------------------------

    async def _ensure_session(self) -> Any:
        """Starts the browser and logs in once; later calls reuse the same context."""
        async with self._lock:
            if self._context is not None:
                return self._context

            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
            opts: dict[str, Any] = {"viewport": self._viewport}
            if self._user_agent:
                opts["user_agent"] = self._user_agent
            self._context = await self._browser.new_context(**opts)

            if self._login_url:
                await self._login()
            return self._context

    async def _login(self) -> None:
        """Drives the login form so the browser holds the antiforgery token and auth cookie."""
        if not self._username or not self._password:
            raise FetchError(
                "login needs `username` and `password` in fetcher_options "
                "(use secret://env/NAME references)",
                transient=False,
            )

        page = await self._context.new_page()
        try:
            await page.goto(
                self._login_url, wait_until="domcontentloaded", timeout=self._timeout_ms
            )
            await page.fill(self._username_selector, self._username)
            await page.fill(self._password_selector, self._password)
            await page.click(self._submit_selector)
            await page.wait_for_load_state("networkidle", timeout=self._timeout_ms)

            if await page.query_selector(self._logged_out_selector):
                raise FetchError(
                    f"login rejected: still on the login form at {page.url}", transient=False
                )
        except FetchError:
            raise
        except Exception as err:  # noqa: BLE001 — normalize browser errors
            raise FetchError(f"login failed: {err!r}", transient=True) from err
        finally:
            await page.close()

    # -- fetch -----------------------------------------------------------

    async def fetch(self, request: ScrapeRequest) -> Response:
        """Navigates to the URL in the logged-in session and returns the rendered HTML."""
        started = time.monotonic()
        context = await self._ensure_session()
        page = await context.new_page()
        try:
            reply = await page.goto(
                request.url, wait_until=self._wait_until, timeout=self._timeout_ms
            )
            if self._wait_selector:
                await page.wait_for_selector(self._wait_selector, timeout=self._timeout_ms)
            if self._wait_after_s > 0:
                await asyncio.sleep(self._wait_after_s)

            if self._paginate_next_selector:
                await self._merge_paged_rows(page)

            body = (await page.content()).encode("utf-8")
            status = reply.status if reply is not None else 200
            headers = dict(reply.headers) if reply is not None else {}
        except Exception as err:  # noqa: BLE001 — normalize every browser error to a typed one
            raise FetchError(f"{request.url}: {err!r}", transient=True) from err
        finally:
            await page.close()

        return Response(
            status=status,
            headers=headers,
            body=body,
            elapsed_ms=(time.monotonic() - started) * 1000,
            content_type="text/html",
        )

    async def _merge_paged_rows(self, page: Any) -> None:
        """Clicks through the remaining pages, appending each page's rows to the first."""
        # Seed the accumulator with page 1 *before* any click, or its rows are
        # lost the moment the grid repaints.
        await page.evaluate(
            """([container, rowSel]) => {
                const sink = document.querySelector(container);
                window.__scrapedRows = sink
                    ? [...sink.querySelectorAll(rowSel)].map(r => r.outerHTML)
                    : [];
            }""",
            [self._paginate_row_container, self._paginate_row_selector],
        )

        seen_pages = 1
        while seen_pages < self._paginate_max_pages:
            nxt = await page.query_selector(self._paginate_next_selector)
            if nxt is None or not await nxt.is_enabled():
                break

            # Snapshot the current first row so we can tell when the grid repaints.
            before = await page.evaluate(
                """(sel) => {
                    const r = document.querySelector(sel);
                    return r ? r.textContent : "";
                }""",
                f"{self._paginate_row_container} {self._paginate_row_selector}",
            )

            await nxt.click()
            try:
                await page.wait_for_function(
                    """([sel, before]) => {
                        const r = document.querySelector(sel);
                        return r && r.textContent !== before;
                    }""",
                    arg=[f"{self._paginate_row_container} {self._paginate_row_selector}", before],
                    timeout=self._timeout_ms,
                )
            except Exception:  # noqa: BLE001 — a stalled repaint just ends pagination
                break

            # Append the freshly rendered page's rows to the accumulator.
            await page.evaluate(
                """([container, rowSel]) => {
                    const sink = document.querySelector(container);
                    if (!sink) return;
                    window.__scrapedRows = window.__scrapedRows || [];
                    for (const r of sink.querySelectorAll(rowSel)) {
                        const html = r.outerHTML;
                        if (!window.__scrapedRows.includes(html)) {
                            window.__scrapedRows.push(html);
                        }
                    }
                }""",
                [self._paginate_row_container, self._paginate_row_selector],
            )
            seen_pages += 1

        # Replay every collected row into the live table before the HTML is read.
        await page.evaluate(
            """([container, rowSel]) => {
                if (!window.__scrapedRows || !window.__scrapedRows.length) return;
                const sink = document.querySelector(container);
                if (!sink) return;
                sink.innerHTML = window.__scrapedRows.join("");
            }""",
            [self._paginate_row_container, self._paginate_row_selector],
        )

    async def aclose(self) -> None:
        """Closes the browser and the Playwright driver."""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

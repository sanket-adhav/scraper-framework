"""A minimal fake Playwright browser for unit tests — no real Chromium needed.

Mimics just the async surface PlaywrightFetcher and FormLoginProvider use:
browser.new_context → context.new_page → page.goto/content, plus cookies.
"""

from __future__ import annotations

from typing import Any


class FakeResponse:
    """Stands in for a Playwright navigation response."""

    def __init__(self, status: int, headers: dict[str, str]) -> None:
        """Holds the status and headers a goto() would return."""
        self.status = status
        self.headers = headers


class FakePage:
    """A fake page that serves canned HTML and records form interactions."""

    def __init__(self, pages: dict[str, str], log: list[str]) -> None:
        """Remembers the url→html map and a shared interaction log."""
        self._pages = pages
        self._log = log
        self._html = "<html><body>empty</body></html>"

    async def goto(self, url: str, wait_until: str = "load", timeout: float = 0) -> FakeResponse:
        """Loads the canned HTML for the URL and returns a 200 response."""
        self._log.append(f"goto:{url}")
        self._html = self._pages.get(url, f"<html><body>rendered {url}</body></html>")
        return FakeResponse(200, {"content-type": "text/html; charset=utf-8"})

    async def content(self) -> str:
        """Returns the current page HTML."""
        return self._html

    async def fill(self, selector: str, value: str) -> None:
        """Records a form fill."""
        self._log.append(f"fill:{selector}={value}")

    async def click(self, selector: str) -> None:
        """Records a form submit click."""
        self._log.append(f"click:{selector}")

    async def wait_for_selector(self, selector: str) -> None:
        """Records a success-check wait."""
        self._log.append(f"wait:{selector}")

    async def close(self) -> None:
        """Records page close."""
        self._log.append("page.close")


class FakeContext:
    """A fake browser context that mints pages and holds cookies."""

    def __init__(
        self, pages: dict[str, str], log: list[str], cookies: list[dict[str, str]]
    ) -> None:
        """Remembers the page map, the log, and the cookies to hand back."""
        self._pages = pages
        self._log = log
        self._cookies = cookies

    async def new_page(self) -> FakePage:
        """Creates a new fake page."""
        self._log.append("new_page")
        return FakePage(self._pages, self._log)

    async def cookies(self) -> list[dict[str, str]]:
        """Returns the context's cookies (as Playwright would)."""
        return self._cookies

    async def close(self) -> None:
        """Records context close."""
        self._log.append("context.close")


class FakeBrowser:
    """A fake browser that mints contexts and records lifecycle events."""

    def __init__(
        self,
        pages: dict[str, str] | None = None,
        cookies: list[dict[str, str]] | None = None,
    ) -> None:
        """Sets up the canned pages, cookies, and an interaction log."""
        self._pages = pages or {}
        self._cookies = cookies or []
        self.log: list[str] = []
        self.contexts_created = 0

    async def new_context(self, **options: Any) -> FakeContext:
        """Creates a new fake context, recording any proxy option."""
        self.contexts_created += 1
        proxy = options.get("proxy") or {}
        self.log.append(f"new_context:{proxy.get('server', '-')}")
        return FakeContext(self._pages, self.log, self._cookies)

    async def close(self) -> None:
        """Records browser close."""
        self.log.append("browser.close")


def fake_browser_factory(browser: FakeBrowser):
    """Returns an async factory that yields the given fake browser."""

    async def factory() -> FakeBrowser:
        """Async no-op that returns the pre-built fake browser."""
        return browser

    return factory

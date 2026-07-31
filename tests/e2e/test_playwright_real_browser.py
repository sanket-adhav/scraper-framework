"""Opt-in e2e: the REAL Playwright browser renders a JS page and the fetcher
returns it as a normal Response. Skips cleanly when Chromium isn't installed,
so the offline suite is unaffected; CI installs Chromium so this actually runs."""

import pytest

from components.fetchers.playwright_fetcher import PlaywrightFetcher
from core.models import ScrapeRequest


def _chromium_available() -> bool:
    """True if a Chromium build is installed for Playwright."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
        import os

        return bool(path) and os.path.exists(path)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _chromium_available(),
    reason="Playwright Chromium not installed (run: playwright install chromium)",
)


class TestRealBrowser:
    async def test_renders_js_generated_content(self):
        """A page whose content is written by JavaScript comes back rendered —
        the whole point of the browser fetcher vs. the HTTP fetcher."""
        fetcher = PlaywrightFetcher(context_pool_size=1)
        html = (
            "data:text/html,<html><body><div id=app></div>"
            "<script>document.getElementById('app').textContent='rendered-by-js';</script>"
            "</body></html>"
        )
        try:
            response = await fetcher.fetch(ScrapeRequest(url=html))
        finally:
            await fetcher.aclose()
        assert response.status == 200
        assert b"rendered-by-js" in response.body  # JS actually executed

    async def test_produces_same_response_model_as_http(self):
        fetcher = PlaywrightFetcher(context_pool_size=1)
        try:
            response = await fetcher.fetch(
                ScrapeRequest(url="data:text/html,<html><body>plain</body></html>")
            )
        finally:
            await fetcher.aclose()
        assert response.content_type == "text/html"
        assert isinstance(response.body, bytes)
        assert response.elapsed_ms >= 0

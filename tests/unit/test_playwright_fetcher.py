"""PlaywrightFetcher tests using a fake browser (no real Chromium).

The DoD 'same Response, downstream can't tell which fetcher ran' is proven by
running the shared FetcherContractSuite against it, and by an integration test
that swaps http→playwright by config alone."""

from components.fetchers.playwright_fetcher import PlaywrightFetcher
from core.models import ScrapeRequest
from tests.contract.base_suites import FetcherContractSuite
from tests.fake_browser import FakeBrowser, fake_browser_factory


def fetcher_over(browser: FakeBrowser, **kw) -> PlaywrightFetcher:
    """Builds a PlaywrightFetcher wired to a fake browser."""
    return PlaywrightFetcher(browser_factory=fake_browser_factory(browser), **kw)


class TestPlaywrightFetcherContract(FetcherContractSuite):
    """Contract conformance for PlaywrightFetcher — the same suite HttpFetcher passes."""

    def make_component(self):
        return fetcher_over(FakeBrowser())

    def make_request(self):
        return ScrapeRequest(url="https://shop.example/item")


class TestRendering:
    async def test_returns_rendered_html_as_response(self):
        browser = FakeBrowser(pages={"https://x.example": "<html><body>hi JS</body></html>"})
        response = await fetcher_over(browser).fetch(ScrapeRequest(url="https://x.example"))
        assert response.status == 200
        assert response.content_type == "text/html"
        assert b"hi JS" in response.body

    async def test_context_is_reused_from_the_pool(self):
        browser = FakeBrowser()
        fetcher = fetcher_over(browser, context_pool_size=1)
        for _ in range(3):
            await fetcher.fetch(ScrapeRequest(url="https://x.example/p"))
        assert browser.contexts_created == 1  # pooled, not one-per-fetch

    async def test_context_recycled_after_n_uses(self):
        browser = FakeBrowser()
        fetcher = fetcher_over(browser, context_pool_size=1, recycle_after=2)
        for _ in range(4):
            await fetcher.fetch(ScrapeRequest(url="https://x.example/p"))
        assert browser.contexts_created == 2  # recycled once after 2 uses

    async def test_per_request_proxy_forces_fresh_context(self):
        browser = FakeBrowser()
        fetcher = fetcher_over(browser)
        req = ScrapeRequest(url="https://x.example", metadata={"proxy": "http://p:8080"})
        await fetcher.fetch(req)
        assert any("http://p:8080" in entry for entry in browser.log)

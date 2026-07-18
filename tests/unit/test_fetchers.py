"""Fetcher tests: HttpFetcher over a mock transport (offline) and LocalFileFetcher."""

import httpx
import pytest

from components.fetchers.http_fetcher import HttpFetcher
from components.fetchers.local_file_fetcher import LocalFileFetcher
from core.errors.exceptions import FetchError
from core.models import ScrapeRequest
from tests.contract.base_suites import FetcherContractSuite
from tests.helpers import FIXTURES_DIR


def http_fetcher(handler) -> HttpFetcher:
    """Builds an HttpFetcher whose 'network' is the given mock handler."""
    return HttpFetcher(transport=httpx.MockTransport(handler))


class TestHttpFetcherContract(FetcherContractSuite):
    """Contract conformance for HttpFetcher (offline via mock transport)."""

    def make_component(self):
        return http_fetcher(lambda request: httpx.Response(200, text="ok"))

    def make_request(self):
        return ScrapeRequest(url="https://shop.example/item")


class TestLocalFileFetcherContract(FetcherContractSuite):
    """Contract conformance for LocalFileFetcher."""

    def make_component(self):
        return LocalFileFetcher(root=FIXTURES_DIR)

    def make_request(self):
        return ScrapeRequest(url="file://sample_product.html")


class TestHttpFetcher:
    async def test_maps_response_fields(self):
        def handler(request: httpx.Request) -> httpx.Response:
            headers = {"content-type": "application/json; charset=utf-8"}
            return httpx.Response(201, text='{"ok": true}', headers=headers)

        response = await http_fetcher(handler).fetch(ScrapeRequest(url="https://api.example/v1"))
        assert response.status == 201
        assert response.body == b'{"ok": true}'
        assert response.content_type == "application/json"  # charset stripped
        assert response.elapsed_ms >= 0

    async def test_sends_method_headers_cookies(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["accept"] = request.headers.get("accept")
            seen["cookie"] = request.headers.get("cookie")
            return httpx.Response(200)

        request = ScrapeRequest(
            url="https://api.example/v1",
            method="POST",
            headers={"Accept": "application/json"},
            cookies={"session": "abc"},
        )
        await http_fetcher(handler).fetch(request)
        assert seen == {"method": "POST", "accept": "application/json", "cookie": "session=abc"}

    async def test_network_errors_are_transient(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection reset")

        with pytest.raises(FetchError) as err:
            await http_fetcher(handler).fetch(ScrapeRequest(url="https://down.example"))
        assert err.value.transient is True

    async def test_timeouts_are_transient(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow")

        with pytest.raises(FetchError) as err:
            await http_fetcher(handler).fetch(ScrapeRequest(url="https://slow.example"))
        assert err.value.transient is True

    async def test_error_statuses_are_returned_not_raised(self):
        """Middleware judges statuses; the fetcher just reports them honestly."""
        response = await http_fetcher(lambda r: httpx.Response(503)).fetch(
            ScrapeRequest(url="https://busy.example")
        )
        assert response.status == 503


class TestLocalFileFetcher:
    async def test_serves_fixture_with_guessed_content_type(self):
        fetcher = LocalFileFetcher(root=FIXTURES_DIR)
        response = await fetcher.fetch(ScrapeRequest(url="file://sample_product.html"))
        assert response.status == 200
        assert response.content_type == "text/html"
        assert b"Aurora X2" in response.body

    async def test_missing_file_is_permanent_error(self):
        fetcher = LocalFileFetcher(root=FIXTURES_DIR)
        with pytest.raises(FetchError) as err:
            await fetcher.fetch(ScrapeRequest(url="file://nope.html"))
        assert err.value.transient is False

    async def test_non_file_scheme_rejected(self):
        with pytest.raises(FetchError, match="file://"):
            await LocalFileFetcher().fetch(ScrapeRequest(url="https://x.example"))

    async def test_cannot_escape_root(self):
        fetcher = LocalFileFetcher(root=FIXTURES_DIR)
        with pytest.raises(FetchError, match="escapes"):
            await fetcher.fetch(ScrapeRequest(url="file://../../etc/passwd"))

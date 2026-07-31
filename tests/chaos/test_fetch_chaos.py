"""Chaos tests: timeouts, 429s, and connection resets injected under the full
YAML-composed middleware stack (Plan 04). Zero network — mock transport only."""

import httpx
import pytest

from cli.composition import build_fetch_stage, default_registry
from components.fetchers.http_fetcher import HttpFetcher
from core.config.loader import load_config
from core.errors.exceptions import FetchError
from core.models import ScrapeRequest
from core.pipeline.context import Context


def make_ctx(url: str = "https://shop.example/item") -> Context:
    """Builds a context carrying one request."""
    return Context(
        trace_id="t-chaos", config={}, config_fingerprint="fp", request=ScrapeRequest(url=url)
    )


def stack_over(handler) -> object:
    """Builds the standard Phase-1 stack (fast test timings) over a mock transport."""
    registry = default_registry()
    registry.register(
        "fetcher", "mock_http", lambda: HttpFetcher(transport=httpx.MockTransport(handler))
    )
    config = load_config(
        [
            {
                "fetcher": "mock_http",
                "middleware": ["retry", "rate_limit", "block_detection", "observability"],
                "middleware_options": {
                    "rate_limit": {"rate": 10000.0, "burst": 100.0},
                    "retry": {"max_attempts": 3, "base_delay_s": 0.0001, "max_delay_s": 0.001},
                },
            }
        ]
    )
    return build_fetch_stage(registry, config.data)


class TestChaosThroughFullStack:
    async def test_timeout_then_recovery(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ReadTimeout("slow upstream")
            return httpx.Response(200, text="fine now")

        ctx = await stack_over(handler).run(make_ctx())
        assert ctx.response is not None and ctx.response.status == 200
        assert calls["n"] == 2  # one timeout, one success

    async def test_429_storm_then_recovery(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] <= 2:
                return httpx.Response(429, headers={"retry-after": "0"})
            return httpx.Response(200, text="welcome back")

        ctx = await stack_over(handler).run(make_ctx())
        assert ctx.response is not None and ctx.response.status == 200
        assert calls["n"] == 3

    async def test_connection_resets_exhaust_budget_and_surface_transient(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection reset by peer")

        with pytest.raises(FetchError) as err:
            await stack_over(handler).run(make_ctx())
        assert err.value.transient is True  # honest signal for the stage/policy layer

    async def test_hard_block_is_permanent_despite_retry_budget(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(403, text="forbidden")

        with pytest.raises(FetchError) as err:
            await stack_over(handler).run(make_ctx())
        assert err.value.blocked is True
        assert calls["n"] == 1  # block detected once; retry never touched it

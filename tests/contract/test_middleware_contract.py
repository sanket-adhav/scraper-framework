"""Middleware contract suite runs + the onion-order tests for the composer."""

import pytest

from components.middleware.block_detection import BlockDetectionMiddleware
from components.middleware.observability import ObservabilityMiddleware
from components.middleware.rate_limiter import RateLimiterMiddleware
from components.middleware.retry import RetryMiddleware
from core.errors.exceptions import FetchError
from core.middleware_runner import compose
from core.models import Response, ScrapeRequest
from tests.contract.base_suites import MiddlewareContractSuite


async def no_sleep(seconds: float) -> None:
    """A sleep that doesn't — keeps middleware tests instant."""


class TestRateLimiterContract(MiddlewareContractSuite):
    """Contract conformance for the rate limiter."""

    def make_component(self):
        return RateLimiterMiddleware(rate=1000.0, burst=10.0, sleep_fn=no_sleep)


class TestRetryContract(MiddlewareContractSuite):
    """Contract conformance for retry."""

    def make_component(self):
        return RetryMiddleware(sleep_fn=no_sleep)


class TestBlockDetectionContract(MiddlewareContractSuite):
    """Contract conformance for block detection (clean responses pass through)."""

    def make_component(self):
        return BlockDetectionMiddleware()


class TestObservabilityContract(MiddlewareContractSuite):
    """Contract conformance for observability."""

    def make_component(self):
        return ObservabilityMiddleware()


class TagMiddleware:
    """Test middleware that logs entering and leaving, to prove onion order."""

    def __init__(self, tag: str, log: list[str]):
        """Remembers its tag and the shared log."""
        self.tag = tag
        self.log = log

    async def __call__(self, request, next):
        """Logs in, calls the next layer, logs out."""
        self.log.append(f"{self.tag}:in")
        response = await next(request)
        self.log.append(f"{self.tag}:out")
        return response


class ShortCircuitMiddleware:
    """Test middleware that answers directly without calling next (like a cache hit)."""

    async def __call__(self, request, next):
        """Returns a canned response; the inner stack never runs."""
        return Response(status=299)


async def fetch_ok(request: ScrapeRequest) -> Response:
    """A fake innermost fetch that always succeeds."""
    return Response(status=200)


class TestComposer:
    """The middleware_runner composer: order, short-circuit, error passthrough."""

    async def test_onion_order_first_is_outermost(self):
        log: list[str] = []
        entry = compose([TagMiddleware("a", log), TagMiddleware("b", log)], fetch_ok)
        await entry(ScrapeRequest(url="https://x.example"))
        assert log == ["a:in", "b:in", "b:out", "a:out"]

    async def test_reordering_the_list_reorders_execution(self):
        """Same objects, reversed list — the onion flips. This is the config-only
        reordering property the YAML test exercises end-to-end."""
        log: list[str] = []
        a, b = TagMiddleware("a", log), TagMiddleware("b", log)
        await compose([b, a], fetch_ok)(ScrapeRequest(url="https://x.example"))
        assert log == ["b:in", "a:in", "a:out", "b:out"]

    async def test_short_circuit_skips_inner_layers(self):
        log: list[str] = []
        entry = compose(
            [TagMiddleware("outer", log), ShortCircuitMiddleware(), TagMiddleware("inner", log)],
            fetch_ok,
        )
        response = await entry(ScrapeRequest(url="https://x.example"))
        assert response.status == 299
        assert log == ["outer:in", "outer:out"]  # inner never entered

    async def test_empty_stack_is_just_the_fetch(self):
        response = await compose([], fetch_ok)(ScrapeRequest(url="https://x.example"))
        assert response.status == 200

    async def test_fetch_errors_pass_through_untouched(self):
        async def fetch_fail(request: ScrapeRequest) -> Response:
            raise FetchError("down", transient=True)

        entry = compose([TagMiddleware("a", [])], fetch_fail)
        with pytest.raises(FetchError, match="down"):
            await entry(ScrapeRequest(url="https://x.example"))

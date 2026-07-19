"""Tests for the Plan 07 middleware: circuit breaker, cache, proxy rotation,
UA rotation, cookie manager, cost tracker — plus contract-suite conformance."""

import pytest

from components.middleware.caching import CachingMiddleware
from components.middleware.circuit_breaker import (
    CircuitBreakerMiddleware,
    CircuitState,
    OpenCircuitError,
)
from components.middleware.cookie_manager import CookieManagerMiddleware
from components.middleware.cost_tracker import CostTrackerMiddleware
from components.middleware.proxy_rotation import ProxyRotationMiddleware
from components.middleware.ua_rotation import UaRotationMiddleware
from core.errors.exceptions import FetchError
from core.models import Response, ScrapeRequest
from tests.contract.base_suites import MiddlewareContractSuite

REQ = ScrapeRequest(url="https://shop.example/item")


async def ok(request):
    """A next() that always returns 200."""
    return Response(status=200, body=b"hello")


class FakeClock:
    """A controllable monotonic clock."""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now


# --- contract conformance for the pass-through-capable middleware ---


class TestCircuitBreakerContract(MiddlewareContractSuite):
    def make_component(self):
        return CircuitBreakerMiddleware()


class TestCacheContract(MiddlewareContractSuite):
    def make_component(self):
        return CachingMiddleware()


class TestUaContract(MiddlewareContractSuite):
    def make_component(self):
        return UaRotationMiddleware()


class TestCookieContract(MiddlewareContractSuite):
    def make_component(self):
        return CookieManagerMiddleware()


class TestCostContract(MiddlewareContractSuite):
    def make_component(self):
        return CostTrackerMiddleware()


# --- circuit breaker ---


class TestCircuitBreaker:
    async def test_opens_after_threshold_then_fails_fast(self):
        clock = FakeClock()
        cb = CircuitBreakerMiddleware(failure_threshold=3, cooldown_s=10, time_fn=clock.time)

        async def boom(request):
            raise FetchError("down", transient=True)

        for _ in range(3):
            with pytest.raises(FetchError):
                await cb(REQ, boom)
        assert cb.state_for("shop.example") is CircuitState.OPEN
        # now it fails fast without calling through
        with pytest.raises(OpenCircuitError):
            await cb(REQ, ok)

    async def test_half_open_probe_then_close_on_success(self):
        clock = FakeClock()
        cb = CircuitBreakerMiddleware(failure_threshold=1, cooldown_s=10, time_fn=clock.time)

        async def boom(request):
            raise FetchError("down", transient=True)

        with pytest.raises(FetchError):
            await cb(REQ, boom)  # opens
        clock.now = 11  # cooldown elapsed
        await cb(REQ, ok)  # half-open probe succeeds → closes
        assert cb.state_for("shop.example") is CircuitState.CLOSED

    async def test_half_open_probe_failure_reopens(self):
        clock = FakeClock()
        cb = CircuitBreakerMiddleware(failure_threshold=1, cooldown_s=10, time_fn=clock.time)

        async def boom(request):
            raise FetchError("down", transient=True)

        with pytest.raises(FetchError):
            await cb(REQ, boom)
        clock.now = 11
        with pytest.raises(FetchError):
            await cb(REQ, boom)  # probe fails → reopen
        assert cb.state_for("shop.example") is CircuitState.OPEN

    async def test_domains_isolated(self):
        cb = CircuitBreakerMiddleware(failure_threshold=1, cooldown_s=10)

        async def boom(request):
            raise FetchError("down", transient=True)

        with pytest.raises(FetchError):
            await cb(ScrapeRequest(url="https://a.example"), boom)
        assert cb.state_for("a.example") is CircuitState.OPEN
        assert cb.state_for("b.example") is CircuitState.CLOSED


# --- cache ---


class TestCache:
    async def test_second_request_served_from_cache(self):
        cache = CachingMiddleware(ttl_s=100)
        calls = {"n": 0}

        async def counting(request):
            calls["n"] += 1
            return Response(status=200, body=b"x")

        await cache(REQ, counting)
        await cache(REQ, counting)
        assert calls["n"] == 1  # second served from cache
        assert cache.hits == 1 and cache.misses == 1

    async def test_expired_entry_refetches(self):
        clock = FakeClock()
        cache = CachingMiddleware(ttl_s=10, time_fn=clock.time)
        calls = {"n": 0}

        async def counting(request):
            calls["n"] += 1
            return Response(status=200)

        await cache(REQ, counting)
        clock.now = 11
        await cache(REQ, counting)
        assert calls["n"] == 2

    async def test_error_responses_never_cached(self):
        cache = CachingMiddleware()
        calls = {"n": 0}

        async def erroring(request):
            calls["n"] += 1
            return Response(status=500)

        await cache(REQ, erroring)
        await cache(REQ, erroring)
        assert calls["n"] == 2  # 500s are not cached

    async def test_blocked_fetch_never_cached(self):
        cache = CachingMiddleware()

        async def blocked(request):
            raise FetchError("captcha", transient=False, blocked=True)

        with pytest.raises(FetchError):
            await cache(REQ, blocked)
        with pytest.raises(FetchError):
            await cache(REQ, blocked)  # still calls through, nothing pinned


# --- proxy rotation ---


class TestProxyRotation:
    async def test_round_robins_proxies(self):
        seen = []

        async def capture(request):
            seen.append(request.metadata["proxy"])
            return Response(status=200)

        pr = ProxyRotationMiddleware(proxies=["http://p1", "http://p2"])
        for _ in range(3):
            await pr(REQ, capture)
        assert seen == ["http://p1", "http://p2", "http://p1"]

    async def test_blocked_proxy_goes_on_cooldown(self):
        clock = FakeClock()
        pr = ProxyRotationMiddleware(
            proxies=["http://p1", "http://p2"], cooldown_s=60, time_fn=clock.time
        )
        seen = []

        async def block_p1(request):
            seen.append(request.metadata["proxy"])
            if request.metadata["proxy"] == "http://p1":
                raise FetchError("blocked", transient=False, blocked=True)
            return Response(status=200)

        with pytest.raises(FetchError):
            await pr(REQ, block_p1)  # p1 blocked → cooldown
        await pr(REQ, block_p1)  # p2
        await pr(REQ, block_p1)  # p1 still cooling → p2 again
        assert seen[1:] == ["http://p2", "http://p2"]

    async def test_all_on_cooldown_raises_transient(self):
        clock = FakeClock()
        pr = ProxyRotationMiddleware(proxies=["http://p1"], cooldown_s=60, time_fn=clock.time)

        async def always_block(request):
            raise FetchError("blocked", transient=False, blocked=True)

        with pytest.raises(FetchError):
            await pr(REQ, always_block)  # p1 now cooling
        with pytest.raises(FetchError, match="cooldown"):
            await pr(REQ, ok)

    def test_empty_pool_rejected(self):
        with pytest.raises(ValueError, match="at least one proxy"):
            ProxyRotationMiddleware(proxies=[])


# --- UA rotation ---


class TestUaRotation:
    async def test_applies_coherent_profile_headers(self):
        seen = []

        async def capture(request):
            seen.append(dict(request.headers))
            return Response(status=200)

        ua = UaRotationMiddleware()
        await ua(REQ, capture)
        headers = seen[0]
        assert "User-Agent" in headers and "Sec-CH-UA-Platform" in headers
        # UA and platform hint agree (coherent profile)
        if "Windows" in headers["User-Agent"]:
            assert headers["Sec-CH-UA-Platform"] == '"Windows"'

    async def test_rotates_and_does_not_override_request_headers(self):
        seen = []

        async def capture(request):
            seen.append(request.headers["User-Agent"])
            return Response(status=200)

        ua = UaRotationMiddleware()
        await ua(REQ, capture)
        await ua(REQ, capture)
        assert seen[0] != seen[1]  # rotated

        # a request that sets its own UA keeps it
        held = ScrapeRequest(url="https://shop.example", headers={"User-Agent": "MyBot/1.0"})
        await ua(held, capture)
        assert seen[2] == "MyBot/1.0"


# --- cookie manager ---


class TestCookieManager:
    async def test_harvests_and_replays_cookies(self):
        cm = CookieManagerMiddleware()
        seen = []

        async def server(request):
            seen.append(dict(request.cookies))
            return Response(status=200, headers={"set-cookie": "sid=abc; Path=/"})

        await cm(REQ, server)  # first request: no cookies, server sets sid
        await cm(REQ, server)  # second: sid replayed
        assert seen[0] == {}
        assert seen[1] == {"sid": "abc"}
        assert cm.cookies_for("shop.example") == {"sid": "abc"}


# --- cost tracker ---


class TestCostTracker:
    async def test_counts_fetches_and_bytes_per_plugin(self):
        ct = CostTrackerMiddleware()
        req = ScrapeRequest(url="https://shop.example", metadata={"plugin": "shop"})
        await ct(req, ok)
        await ct(req, ok)
        counters = ct.by_plugin["shop"]
        assert counters.fetches == 2
        assert counters.bytes_downloaded == 10  # "hello" x2

    async def test_browser_mode_counts_time(self):
        clock = FakeClock()
        ct = CostTrackerMiddleware(browser=True, time_fn=clock.time)

        async def slow(request):
            clock.now += 5
            return Response(status=200)

        await ct(ScrapeRequest(url="https://x.example", metadata={"plugin": "p"}), slow)
        assert ct.by_plugin["p"].browser_seconds == 5

    async def test_errors_counted(self):
        ct = CostTrackerMiddleware()

        async def boom(request):
            raise FetchError("x", transient=True)

        with pytest.raises(FetchError):
            await ct(ScrapeRequest(url="https://x.example", metadata={"plugin": "p"}), boom)
        assert ct.by_plugin["p"].errors == 1

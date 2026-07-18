"""Rate limiter tests: per-domain isolation, burst behavior, faked clock."""

from components.middleware.rate_limiter import RateLimiterMiddleware
from core.models import Response, ScrapeRequest


class FakeClock:
    """A controllable monotonic clock plus a sleep that advances it instantly."""

    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


async def fetch_ok(request: ScrapeRequest) -> Response:
    """Fake fetch that always succeeds instantly."""
    return Response(status=200)


def limiter(rate: float, burst: float, clock: FakeClock, **kw) -> RateLimiterMiddleware:
    """Builds a rate limiter wired to the fake clock."""
    return RateLimiterMiddleware(
        rate=rate, burst=burst, time_fn=clock.time, sleep_fn=clock.sleep, **kw
    )


class TestRateLimiter:
    async def test_burst_goes_through_then_waits(self):
        clock = FakeClock()
        rl = limiter(rate=1.0, burst=2.0, clock=clock)
        req = ScrapeRequest(url="https://a.example/x")
        for _ in range(2):  # burst capacity: no waiting
            await rl(req, fetch_ok)
        assert clock.slept == []
        await rl(req, fetch_ok)  # third must wait for a refill
        assert len(clock.slept) == 1
        assert clock.slept[0] > 0

    async def test_domains_have_isolated_budgets(self):
        clock = FakeClock()
        rl = limiter(rate=1.0, burst=1.0, clock=clock)
        await rl(ScrapeRequest(url="https://a.example/1"), fetch_ok)
        await rl(ScrapeRequest(url="https://b.example/1"), fetch_ok)  # different domain: no wait
        assert clock.slept == []
        await rl(ScrapeRequest(url="https://a.example/2"), fetch_ok)  # same domain: waits
        assert len(clock.slept) == 1

    async def test_tokens_refill_over_time(self):
        clock = FakeClock()
        rl = limiter(rate=2.0, burst=1.0, clock=clock)
        req = ScrapeRequest(url="https://a.example/x")
        await rl(req, fetch_ok)
        clock.now += 0.5  # exactly one token refilled at rate=2/s
        await rl(req, fetch_ok)
        assert clock.slept == []

    async def test_per_domain_config_override(self):
        clock = FakeClock()
        rl = limiter(
            rate=1.0, burst=1.0, clock=clock,
            domains={"fast.example": {"rate": 100.0, "burst": 50.0}},
        )
        for i in range(20):  # generous override: no waiting
            await rl(ScrapeRequest(url=f"https://fast.example/{i}"), fetch_ok)
        assert clock.slept == []

    async def test_every_acquisition_is_counted(self):
        """The counter the retry-storm test relies on: attempts are visible."""
        clock = FakeClock()
        rl = limiter(rate=100.0, burst=10.0, clock=clock)
        req = ScrapeRequest(url="https://a.example/x")
        for _ in range(3):
            await rl(req, fetch_ok)
        assert rl.bucket_for("a.example").acquired_count == 3

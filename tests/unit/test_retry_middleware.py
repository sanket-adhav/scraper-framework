"""Retry middleware tests: backoff schedule, budget, permanent errors, Retry-After."""

import pytest

from components.middleware.retry import RetryMiddleware
from core.errors.exceptions import FetchError
from core.models import Response, ScrapeRequest

REQ = ScrapeRequest(url="https://shop.example/item")


class SleepRecorder:
    """Fake sleep that records every requested delay instead of waiting."""

    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class FlakyFetch:
    """Fake fetch that fails N times (or returns given statuses) then succeeds."""

    def __init__(self, failures: int = 0, error: FetchError | None = None, statuses=()):
        self.failures = failures
        self.error = error or FetchError("net down", transient=True)
        self.statuses = list(statuses)
        self.attempts_seen: list[int] = []

    async def __call__(self, request: ScrapeRequest) -> Response:
        self.attempts_seen.append(request.attempt)
        if self.failures > 0:
            self.failures -= 1
            raise self.error
        if self.statuses:
            return Response(status=self.statuses.pop(0))
        return Response(status=200)


class TestRetrySchedule:
    async def test_exponential_backoff_with_jitter_capped(self):
        sleeps = SleepRecorder()
        retry = RetryMiddleware(
            max_attempts=4, base_delay_s=1.0, max_delay_s=3.0, jitter=0.5,
            sleep_fn=sleeps, random_fn=lambda: 1.0,
        )
        response = await retry(REQ, FlakyFetch(failures=3))
        assert response.status == 200
        # delays: 1*2^0, 1*2^1, then capped at 3 — each +50% jitter (random=1.0)
        assert sleeps.delays == [1.5, 3.0, 4.5]

    async def test_gives_up_after_max_attempts(self):
        retry = RetryMiddleware(max_attempts=3, sleep_fn=SleepRecorder())
        fetch = FlakyFetch(failures=99)
        with pytest.raises(FetchError):
            await retry(REQ, fetch)
        assert len(fetch.attempts_seen) == 3

    async def test_attempt_counter_rides_on_the_request(self):
        retry = RetryMiddleware(max_attempts=3, sleep_fn=SleepRecorder())
        fetch = FlakyFetch(failures=2)
        await retry(REQ, fetch)
        assert fetch.attempts_seen == [0, 1, 2]

    async def test_never_retries_permanent_errors(self):
        retry = RetryMiddleware(max_attempts=5, sleep_fn=SleepRecorder())
        fetch = FlakyFetch(failures=99, error=FetchError("blocked", transient=False))
        with pytest.raises(FetchError, match="blocked"):
            await retry(REQ, fetch)
        assert len(fetch.attempts_seen) == 1  # exactly one try, no retry

    async def test_retries_429_and_respects_retry_after(self):
        sleeps = SleepRecorder()
        retry = RetryMiddleware(max_attempts=3, sleep_fn=sleeps)

        class Throttled:
            """Returns a 429 with Retry-After once, then 200."""

            calls = 0

            async def __call__(self, request):
                type(self).calls += 1
                if type(self).calls == 1:
                    return Response(status=429, headers={"retry-after": "7"})
                return Response(status=200)

        response = await retry(REQ, Throttled())
        assert response.status == 200
        assert sleeps.delays == [7.0]  # the server's wish, not our backoff

    async def test_exhausted_retries_on_429_returns_last_response(self):
        """If throttling never lifts, the caller gets the honest 429 back."""
        retry = RetryMiddleware(max_attempts=2, sleep_fn=SleepRecorder())
        response = await retry(REQ, FlakyFetch(statuses=[429, 429]))
        assert response.status == 429

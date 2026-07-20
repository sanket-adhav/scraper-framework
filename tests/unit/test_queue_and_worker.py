"""Hermetic tests for the queue contract, the in-memory queue, and the worker loop —
plus the distributed rate limiter and incremental change detection."""


from datetime import UTC, datetime, timedelta

from components.middleware.distributed_rate_limiter import (
    DistributedRateLimiterMiddleware,
    InMemoryTokenBucketStore,
)
from components.queue.in_memory_queue import InMemoryQueue
from components.scheduler.change_detection import ChangeDetector, is_due
from components.scheduler.checkpoint_store import InMemoryCheckpointStore
from core.contracts.queue import ClaimedJob, QueueProvider
from core.engine.worker import Worker, queue_discovered_sink
from core.models import Response, ScrapeRequest
from core.models.job import ScrapeJob
from core.scheduler.incremental_state import Checkpoint


def job(url: str = "https://x.example", priority: int = 0) -> ScrapeJob:
    """Builds a one-request job."""
    return ScrapeJob(requests=(ScrapeRequest(url=url),), priority=priority)


class FakeClock:
    """A controllable clock for lease tests."""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now


class TestInMemoryQueue:
    def test_satisfies_queue_contract(self):
        assert isinstance(InMemoryQueue(), QueueProvider)

    async def test_submit_claim_ack_roundtrip(self):
        q = InMemoryQueue()
        await q.submit(job("https://a.example"))
        assert await q.depth() == 1
        claimed = await q.claim("w1", lease_seconds=60)
        assert isinstance(claimed, ClaimedJob)
        assert claimed.job.requests[0].url == "https://a.example"
        assert await q.depth() == 0  # claimed, not available
        await q.ack(claimed.claim_id)
        assert await q.claim("w1", 60) is None  # nothing left

    async def test_priority_is_honored(self):
        q = InMemoryQueue()
        await q.submit(job("low", priority=1))
        await q.submit(job("high", priority=9))
        first = await q.claim("w1", 60)
        assert first.job.requests[0].url == "high"

    async def test_two_workers_never_get_the_same_job(self):
        q = InMemoryQueue()
        await q.submit(job("only"))
        a = await q.claim("w1", 60)
        b = await q.claim("w2", 60)
        assert a is not None and b is None  # exactly one worker gets it

    async def test_nack_requeues_then_dead_letters(self):
        q = InMemoryQueue(max_attempts=2)
        await q.submit(job("poison"))
        c1 = await q.claim("w1", 60)
        await q.nack(c1.claim_id)  # attempt 1 failed → requeued
        c2 = await q.claim("w1", 60)
        await q.nack(c2.claim_id)  # attempt 2 failed → dead-letter
        assert await q.depth() == 0
        assert len(q.dead_letters) == 1

    async def test_expired_lease_is_reclaimed(self):
        clock = FakeClock()
        q = InMemoryQueue(time_fn=clock.time)
        await q.submit(job("leased"))
        await q.claim("w1", lease_seconds=30)  # worker claims then "crashes"
        assert await q.depth() == 0
        clock.now = 31  # lease expires
        assert await q.reclaim_expired() == 1
        assert await q.depth() == 1  # back to pending, redeliverable


class RecordingEngine:
    """A fake engine that records the jobs it ran (and can be told to fail)."""

    def __init__(self, fail_urls=()):
        self.ran = []
        self._fail = set(fail_urls)

    async def run(self, job):
        self.ran.append(job.requests[0].url)
        if job.requests[0].url in self._fail:
            raise RuntimeError("boom")


class TestWorker:
    async def test_drains_queue_acking_each_job(self):
        q = InMemoryQueue()
        for i in range(3):
            await q.submit(job(f"https://x.example/{i}"))
        engine = RecordingEngine()
        stats = await Worker(q, engine).drain()  # type: ignore[arg-type]
        assert stats.processed == 3 and stats.acked == 3
        assert len(engine.ran) == 3
        assert await q.depth() == 0

    async def test_failing_job_is_nacked_not_fatal(self):
        q = InMemoryQueue(max_attempts=1)
        await q.submit(job("https://bad.example"))
        engine = RecordingEngine(fail_urls={"https://bad.example"})
        stats = await Worker(q, engine).drain()  # type: ignore[arg-type]
        assert stats.nacked == 1
        assert len(q.dead_letters) == 1  # exhausted → dead-letter, worker survived

    async def test_discovered_sink_enqueues_new_jobs(self):
        q = InMemoryQueue()
        sink = queue_discovered_sink(q)
        await sink(ScrapeRequest(url="https://discovered.example"))
        assert await q.depth() == 1
        claimed = await q.claim("w1", 60)
        assert claimed.job.requests[0].url == "https://discovered.example"


class TestDistributedRateLimiter:
    async def test_shared_bucket_limits_combined_rate(self):
        """Two 'workers' sharing one in-memory bucket store see one budget: the
        3rd acquire within the same instant must wait (burst=2)."""
        clock = FakeClock()
        store = InMemoryTokenBucketStore(time_fn=clock.time)
        waits = []

        async def sleep(s):
            waits.append(s)
            clock.now += s

        async def ok(request):
            return Response(status=200)

        mw = DistributedRateLimiterMiddleware(store, rate=1.0, burst=2.0, sleep_fn=sleep)
        req = ScrapeRequest(url="https://shared.example/x")
        await mw(req, ok)  # token 1 (burst)
        await mw(req, ok)  # token 2 (burst)
        await mw(req, ok)  # must wait for a refill
        assert waits and waits[0] > 0

    async def test_domains_have_independent_budgets(self):
        store = InMemoryTokenBucketStore()
        assert await store.try_acquire("a.example", 1.0, 1.0) == 0.0
        assert await store.try_acquire("b.example", 1.0, 1.0) == 0.0  # different domain, free
        assert await store.try_acquire("a.example", 1.0, 1.0) > 0  # a is now empty


class TestChangeDetection:
    def test_unchanged_content_is_skipped(self):
        store = InMemoryCheckpointStore()
        detector = ChangeDetector(store)
        assert detector.changed("sebi", b"<html>v1</html>") is True  # first sight → changed
        assert detector.changed("sebi", b"<html>v1</html>") is False  # identical → skip

    def test_changed_content_is_rescraped(self):
        store = InMemoryCheckpointStore()
        detector = ChangeDetector(store)
        detector.changed("sebi", b"<html>v1</html>")
        assert detector.changed("sebi", b"<html>v2</html>") is True  # new content → re-scrape

    def test_is_due_policy(self):
        now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
        fresh = Checkpoint(source="s", updated_at=now - timedelta(minutes=5))
        old = Checkpoint(source="s", updated_at=now - timedelta(hours=2))
        assert is_due(None, now, min_age_seconds=3600) is True  # never run
        assert is_due(fresh, now, min_age_seconds=3600) is False  # too recent
        assert is_due(old, now, min_age_seconds=3600) is True  # aged out
        assert is_due(fresh, now, min_age_seconds=3600, forced=True) is True  # forced

"""Real-Postgres distributed tests (Plan 09 DoD): SKIP LOCKED queue distribution,
kill-a-worker redelivery, and one shared rate-limit budget across workers.
Skips without DATABASE_URL; runs against the CI Postgres service and locally."""

import asyncio
import os

import pytest

from components.middleware.distributed_rate_limiter import PostgresTokenBucketStore
from components.queue.postgres_queue import PostgresQueue
from components.scheduler.checkpoint_store import PostgresCheckpointStore
from core.models import ScrapeRequest
from core.models.job import ScrapeJob
from core.scheduler.incremental_state import Checkpoint

DATABASE_URL = os.environ.get("SCRAPER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="set SCRAPER_TEST_DATABASE_URL to a throwaway database to run these"
)


async def _reset() -> None:
    """Clears the shared Plan-09 tables so each test starts clean."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        async with conn.cursor() as cur:
            for table in ("scraper_jobs", "rate_limit_buckets", "scraper_checkpoints"):
                await cur.execute(f"DROP TABLE IF EXISTS {table}")
        await conn.commit()


def job(url: str, priority: int = 0) -> ScrapeJob:
    """Builds a one-request job."""
    return ScrapeJob(requests=(ScrapeRequest(url=url),), priority=priority)


class TestPostgresQueue:
    async def test_submit_claim_ack(self):
        await _reset()
        q = PostgresQueue(DATABASE_URL)
        await q.submit(job("https://a.example"))
        assert await q.depth() == 1
        claimed = await q.claim("w1", 60)
        assert claimed is not None and claimed.job.requests[0].url == "https://a.example"
        await q.ack(claimed.claim_id)
        assert await q.depth() == 0

    async def test_skip_locked_distributes_without_double_processing(self):
        """Two workers claiming concurrently get disjoint jobs — the core SKIP
        LOCKED guarantee that makes scaling safe."""
        await _reset()
        q = PostgresQueue(DATABASE_URL)
        for i in range(10):
            await q.submit(job(f"https://x.example/{i}"))
        # 10 concurrent claims across 2 "workers"
        claims = await asyncio.gather(*[q.claim(f"w{i % 2}", 60) for i in range(10)])
        urls = [c.job.requests[0].url for c in claims if c is not None]
        assert len(urls) == 10
        assert len(set(urls)) == 10  # no job handed out twice

    async def test_priority_claimed_first(self):
        await _reset()
        q = PostgresQueue(DATABASE_URL)
        await q.submit(job("low", priority=1))
        await q.submit(job("high", priority=9))
        first = await q.claim("w1", 60)
        assert first.job.requests[0].url == "high"

    async def test_poison_job_dead_letters(self):
        await _reset()
        q = PostgresQueue(DATABASE_URL, max_attempts=2)
        await q.submit(job("poison"))
        c1 = await q.claim("w1", 60)
        await q.nack(c1.claim_id)
        c2 = await q.claim("w1", 60)
        await q.nack(c2.claim_id)  # 2nd failure → dead
        assert await q.depth() == 0
        assert await q.dead_letter_count() == 1

    async def test_kill_a_worker_redelivers_in_flight_job(self):
        """A worker claims a job with a short lease then 'crashes' (never acks);
        reclaim_expired returns it to pending so another worker completes it once."""
        await _reset()
        q = PostgresQueue(DATABASE_URL)
        await q.submit(job("https://inflight.example"))
        claimed = await q.claim("w1", lease_seconds=-1)  # already-expired lease
        assert claimed is not None
        assert await q.depth() == 0  # in-flight, not available
        reclaimed = await q.reclaim_expired()
        assert reclaimed == 1
        assert await q.depth() == 1  # redeliverable
        again = await q.claim("w2", 60)
        assert again.job.requests[0].url == "https://inflight.example"


class TestDistributedRateLimit:
    async def test_shared_budget_across_concurrent_acquirers(self):
        """Two concurrent 'workers' hitting one Postgres bucket (burst=2) get at
        most 2 free tokens; the rest must wait — one budget, not two."""
        await _reset()
        store = PostgresTokenBucketStore(DATABASE_URL)
        waits = await asyncio.gather(
            *[store.try_acquire("shared.example", rate=0.001, burst=2.0) for _ in range(6)]
        )
        free = [w for w in waits if w == 0.0]
        throttled = [w for w in waits if w > 0.0]
        assert len(free) == 2  # exactly the burst budget went through free
        assert len(throttled) == 4  # the rest were told to wait


class TestPostgresCheckpoints:
    def test_checkpoint_survives_reconnect(self):
        """A checkpoint written by one store object is read by a fresh one —
        i.e. it persists across a restart."""
        import psycopg

        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS scraper_checkpoints")
            conn.commit()
        PostgresCheckpointStore(DATABASE_URL).put(
            Checkpoint(source="sebi", cursor="page-2", content_hash="abc123")
        )
        loaded = PostgresCheckpointStore(DATABASE_URL).get("sebi")
        assert loaded is not None
        assert loaded.cursor == "page-2" and loaded.content_hash == "abc123"

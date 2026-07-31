"""The Worker — the unchanged engine plus a queue consume loop (plan2.md §16, Plan 09).

A worker claims a job, runs it through the engine (discovered requests go back to
the queue as new jobs via `queue_discovered_sink`), then acks on success or nacks
on failure. Graceful shutdown finishes the in-flight job first. Run N of these
against one queue and the crawl distributes itself — the engine is identical to
single-process mode.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, replace

from core.contracts.queue import ClaimedJob, QueueProvider
from core.engine.scraper_engine import DiscoveredSink, ScraperEngine
from core.models.job import ScrapeJob
from core.models.scrape_request import ScrapeRequest


@dataclass(frozen=True, slots=True)
class WorkerStats:
    """What one worker did over its run: jobs processed, acked, failed, empties."""

    processed: int = 0
    acked: int = 0
    nacked: int = 0
    idle_polls: int = 0


def queue_discovered_sink(queue: QueueProvider) -> DiscoveredSink:
    """Returns an engine discovered-sink that submits each discovered request to
    the queue as its own new single-request job."""

    async def sink(request: ScrapeRequest) -> None:
        """Wraps one discovered request as a job and queues it."""
        await queue.submit(ScrapeJob(requests=(request,)))

    return sink


class Worker:
    """Consumes jobs from a queue and runs each through the engine until stopped."""

    def __init__(
        self,
        queue: QueueProvider,
        engine: ScraperEngine,
        *,
        worker_id: str | None = None,
        lease_seconds: float = 60.0,
        idle_sleep_s: float = 0.5,
    ) -> None:
        """Stores the queue, engine, this worker's id, the lease length, and idle backoff."""
        self._queue = queue
        self._engine = engine
        self._worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._lease_seconds = lease_seconds
        self._idle_sleep_s = idle_sleep_s
        self._stopping = False

    def request_stop(self) -> None:
        """Asks the worker to stop after the current job (graceful shutdown)."""
        self._stopping = True

    async def run_forever(self) -> WorkerStats:
        """Consumes until stopped, sleeping briefly when the queue is empty."""
        stats = WorkerStats()
        while not self._stopping:
            claimed = await self._queue.claim(self._worker_id, self._lease_seconds)
            if claimed is None:
                stats = replace(stats, idle_polls=stats.idle_polls + 1)
                await asyncio.sleep(self._idle_sleep_s)
                continue
            stats = await self._run_claim(claimed, stats)
        return stats

    async def drain(self, max_jobs: int | None = None) -> WorkerStats:
        """Processes jobs until the queue is empty (or max_jobs hit) — used in tests
        and one-shot batch runs. Reclaims expired leases first."""
        await self._queue.reclaim_expired()
        stats = WorkerStats()
        while max_jobs is None or stats.processed < max_jobs:
            claimed = await self._queue.claim(self._worker_id, self._lease_seconds)
            if claimed is None:
                break
            stats = await self._run_claim(claimed, stats)
        return stats

    async def _run_claim(self, claimed: ClaimedJob, stats: WorkerStats) -> WorkerStats:
        """Runs one claimed job through the engine and acks/nacks the queue."""
        try:
            await self._engine.run(claimed.job)
        except Exception:  # noqa: BLE001 — a job blowing up must not kill the worker
            await self._queue.nack(claimed.claim_id)
            return replace(stats, processed=stats.processed + 1, nacked=stats.nacked + 1)
        await self._queue.ack(claimed.claim_id)
        return replace(stats, processed=stats.processed + 1, acked=stats.acked + 1)

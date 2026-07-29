"""In-memory job queue — the hermetic default for single-process runs and tests.
task queue when running multiple parallel scrapers workers on a server.
Implements the same QueueProvider contract as PostgresQueue, so the worker loop
and engine behave identically whether jobs live in a deque or in Postgres.
"""

from __future__ import annotations

import heapq
import itertools
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from core.contracts.queue import ClaimedJob
from core.models.job import ScrapeJob

TimeFn = Callable[[], float]


@dataclass(order=True)
class _Entry:
    """One queued job ordered by (‑priority, insertion order) so higher priority wins."""

    sort_key: tuple[int, int]
    job: ScrapeJob = field(compare=False)
    attempts: int = field(default=0, compare=False)


class InMemoryQueue:
    """A priority job queue held in this process, with leases and dead-lettering."""

    def __init__(self, max_attempts: int = 3, time_fn: TimeFn = time.monotonic) -> None:
        """Sets the retry budget and an injectable clock (for lease tests)."""
        self._max_attempts = max_attempts
        self._time = time_fn
        self._pending: list[_Entry] = []
        self._counter = itertools.count()
        self._in_flight: dict[str, tuple[_Entry, float]] = {}  # claim_id → (entry, lease_expiry)
        self.dead_letters: list[ScrapeJob] = []

    async def submit(self, job: ScrapeJob) -> None:
        """Pushes a job, ordered by priority then arrival."""
        entry = _Entry(sort_key=(-job.priority, next(self._counter)), job=job)
        heapq.heappush(self._pending, entry)

    async def claim(self, worker_id: str, lease_seconds: float) -> ClaimedJob | None:
        """Pops the highest-priority job and leases it to the worker."""
        if not self._pending:
            return None
        entry = heapq.heappop(self._pending)
        claim_id = uuid.uuid4().hex
        self._in_flight[claim_id] = (entry, self._time() + lease_seconds)
        return ClaimedJob(job=entry.job, claim_id=claim_id, attempts=entry.attempts)

    async def ack(self, claim_id: str) -> None:
        """Drops the leased job — it completed successfully."""
        self._in_flight.pop(claim_id, None)

    async def nack(self, claim_id: str) -> None:
        """Requeues the job with an incremented attempt, or dead-letters it."""
        pair = self._in_flight.pop(claim_id, None)
        if pair is None:
            return
        entry, _ = pair
        entry.attempts += 1
        if entry.attempts >= self._max_attempts:
            self.dead_letters.append(entry.job)
        else:
            heapq.heappush(self._pending, entry)

    async def reclaim_expired(self) -> int:
        """Requeues any leased job whose lease has passed (simulating a dead worker)."""
        now = self._time()
        expired = [cid for cid, (_, exp) in self._in_flight.items() if exp <= now]
        for claim_id in expired:
            entry, _ = self._in_flight.pop(claim_id)
            heapq.heappush(self._pending, entry)
        return len(expired)

    async def depth(self) -> int:
        """Returns the number of jobs waiting to be claimed."""
        return len(self._pending)

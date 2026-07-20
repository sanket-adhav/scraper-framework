"""QueueProvider contract — the durable job queue behind distributed workers (Plan 09).

Jobs are the serializable ScrapeJob from Plan 03 (dict round-trip already proven).
A worker claims a job (leased so a crashed worker's job is redelivered), acks on
success, and nacks on failure; too many failures dead-letter the job. The
contract is deliberately small so a Postgres queue now and (if ever needed) a
Redis/RabbitMQ queue later are drop-ins with zero core change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.models.job import ScrapeJob


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """A job handed to a worker, with the token used to ack/nack it."""

    job: ScrapeJob
    claim_id: str
    attempts: int


@runtime_checkable
class QueueProvider(Protocol):
    """Anything that can durably hold jobs and hand them to workers one lease at a time."""

    async def submit(self, job: ScrapeJob) -> None:
        """Adds one job to the queue (priority honored by claim order)."""
        ...

    async def claim(self, worker_id: str, lease_seconds: float) -> ClaimedJob | None:
        """Leases the next due job to a worker, or returns None if the queue is empty."""
        ...

    async def ack(self, claim_id: str) -> None:
        """Marks a claimed job done so it is never redelivered."""
        ...

    async def nack(self, claim_id: str) -> None:
        """Returns a failed job for retry, or dead-letters it once attempts run out."""
        ...

    async def reclaim_expired(self) -> int:
        """Requeues jobs whose lease expired (a crashed worker); returns how many."""
        ...

    async def depth(self) -> int:
        """Returns how many jobs are waiting to be claimed (for autoscaling)."""
        ...

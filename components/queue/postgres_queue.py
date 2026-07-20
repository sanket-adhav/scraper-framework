"""Durable Postgres job queue using SELECT ... FOR UPDATE SKIP LOCKED (Plan 09).

One `scraper_jobs` table is the whole queue — no Redis, no broker. A claim locks
and stamps a row atomically so two workers never get the same job; a lease
(visibility timeout) means a crashed worker's job is reclaimed and redelivered;
bounded attempts dead-letter a poison job. Priority orders the claim.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from core.contracts.queue import ClaimedJob
from core.models.job import ScrapeJob

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS scraper_jobs (
    id           BIGSERIAL PRIMARY KEY,
    job_id       TEXT NOT NULL,
    payload      JSONB NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    claim_id     TEXT,
    lease_expires_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""
_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS scraper_jobs_claimable
    ON scraper_jobs (status, priority DESC, id)
"""


class PostgresQueue:
    """A durable job queue backed by a single Postgres table."""

    def __init__(self, dsn: str, max_attempts: int = 3, connect: Any = None) -> None:
        """Stores the DSN and retry budget; `connect` is an injectable async factory."""
        self._dsn = dsn
        self._max_attempts = max_attempts
        self._connect = connect
        self._ready = False
        self._ensure_lock = asyncio.Lock()

    async def _conn(self) -> Any:
        """Opens a connection via the injected factory or psycopg by default."""
        if self._connect is not None:
            return await self._connect(self._dsn)
        import psycopg

        return await psycopg.AsyncConnection.connect(self._dsn)

    async def _ensure(self, conn: Any) -> None:
        """Creates the queue table and claim index once, serialized and race-tolerant."""
        if self._ready:
            return
        async with self._ensure_lock:
            if self._ready:
                return
            try:
                async with conn.cursor() as cur:
                    await cur.execute(_CREATE_TABLE)
                    await cur.execute(_CREATE_INDEX)
                await conn.commit()
            except Exception:  # noqa: BLE001 — another worker created it first; fine
                await conn.rollback()
            self._ready = True

    async def submit(self, job: ScrapeJob) -> None:
        """Inserts a job as a pending row."""
        conn = await self._conn()
        try:
            await self._ensure(conn)
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO scraper_jobs (job_id, payload, priority) VALUES (%s, %s, %s)",
                    (job.job_id, json.dumps(job.to_dict()), job.priority),
                )
            await conn.commit()
        finally:
            await conn.close()

    async def claim(self, worker_id: str, lease_seconds: float) -> ClaimedJob | None:
        """Atomically claims the top pending job with SKIP LOCKED and leases it."""
        claim_id = uuid.uuid4().hex
        conn = await self._conn()
        try:
            await self._ensure(conn)
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE scraper_jobs SET
                        status = 'in_flight',
                        claim_id = %s,
                        attempts = attempts + 1,
                        lease_expires_at = now() + make_interval(secs => %s)
                    WHERE id = (
                        SELECT id FROM scraper_jobs
                        WHERE status = 'pending'
                        ORDER BY priority DESC, id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING payload, attempts
                    """,
                    (claim_id, lease_seconds),
                )
                row = await cur.fetchone()
            await conn.commit()
            if row is None:
                return None
            payload, attempts = row
            data = payload if isinstance(payload, dict) else json.loads(payload)
            return ClaimedJob(job=ScrapeJob.from_dict(data), claim_id=claim_id, attempts=attempts)
        finally:
            await conn.close()

    async def ack(self, claim_id: str) -> None:
        """Marks the claimed job done."""
        await self._update_status(claim_id, "done")

    async def nack(self, claim_id: str) -> None:
        """Requeues the job, or dead-letters it once attempts hit the limit."""
        conn = await self._conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE scraper_jobs
                    SET status = CASE WHEN attempts >= %s THEN 'dead' ELSE 'pending' END,
                        claim_id = NULL,
                        lease_expires_at = NULL
                    WHERE claim_id = %s
                    """,
                    (self._max_attempts, claim_id),
                )
            await conn.commit()
        finally:
            await conn.close()

    async def reclaim_expired(self) -> int:
        """Returns expired-lease jobs to pending (a crashed worker); returns the count."""
        conn = await self._conn()
        try:
            await self._ensure(conn)
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE scraper_jobs
                    SET status = CASE WHEN attempts >= %s THEN 'dead' ELSE 'pending' END,
                        claim_id = NULL, lease_expires_at = NULL
                    WHERE status = 'in_flight' AND lease_expires_at < now()
                    """,
                    (self._max_attempts,),
                )
                count = cur.rowcount
            await conn.commit()
            return int(count)
        finally:
            await conn.close()

    async def depth(self) -> int:
        """Counts pending jobs waiting to be claimed."""
        conn = await self._conn()
        try:
            await self._ensure(conn)
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM scraper_jobs WHERE status = 'pending'")
                row = await cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            await conn.close()

    async def dead_letter_count(self) -> int:
        """Counts jobs that exhausted their retries (for tests/monitoring)."""
        conn = await self._conn()
        try:
            await self._ensure(conn)
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM scraper_jobs WHERE status = 'dead'")
                row = await cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            await conn.close()

    async def _update_status(self, claim_id: str, status: str) -> None:
        """Sets a claimed row's status and clears its lease."""
        conn = await self._conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE scraper_jobs SET status = %s, lease_expires_at = NULL "
                    "WHERE claim_id = %s",
                    (status, claim_id),
                )
            await conn.commit()
        finally:
            await conn.close()

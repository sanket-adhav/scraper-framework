"""Distributed rate-limit middleware backed by Postgres (plan2.md §16, Plan 09).

The in-memory RateLimiterMiddleware (Plan 04) is per-process; with N workers each
would allow the full budget, so the combined rate is N× the limit — a
self-inflicted DDoS. This variant keeps each domain's token bucket in a Postgres
row, so every worker draws from ONE shared budget. The bucket store is a small
protocol: a Postgres backend for real runs, an in-memory one for hermetic tests.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

from core.contracts.middleware import Next
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

TimeFn = Callable[[], float]
SleepFn = Callable[[float], Awaitable[None]]


@runtime_checkable
class TokenBucketStore(Protocol):
    """A shared per-domain token bucket: take a token or report the wait needed."""

    async def try_acquire(self, domain: str, rate: float, burst: float) -> float:
        """Returns 0.0 if a token was taken, else the seconds to wait and retry."""
        ...


class DistributedRateLimiterMiddleware:
    """Middleware that throttles per domain against a shared (Postgres) token bucket."""

    def __init__(
        self,
        store: TokenBucketStore,
        rate: float = 1.0,
        burst: float = 1.0,
        sleep_fn: SleepFn | None = None,
    ) -> None:
        """Stores the shared bucket backend and the default per-domain budget."""
        self._store = store
        self._rate = rate
        self._burst = burst
        self._sleep: SleepFn = sleep_fn if sleep_fn is not None else asyncio.sleep

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Waits until the domain's shared bucket yields a token, then fetches."""
        domain = urlsplit(request.url).netloc
        while True:
            wait = await self._store.try_acquire(domain, self._rate, self._burst)
            if wait <= 0:
                return await next(request)
            await self._sleep(wait)


class InMemoryTokenBucketStore:
    """A process-local bucket store — for testing the middleware without Postgres."""

    def __init__(self, time_fn: TimeFn = time.monotonic) -> None:
        """Starts with no buckets and an injectable clock."""
        self._buckets: dict[str, tuple[float, float]] = {}  # domain → (tokens, last_ts)
        self._time = time_fn

    async def try_acquire(self, domain: str, rate: float, burst: float) -> float:
        """Refills by elapsed time, then takes a token or returns the wait."""
        now = self._time()
        tokens, last = self._buckets.get(domain, (burst, now))
        tokens = min(burst, tokens + (now - last) * rate)
        if tokens >= 1:
            self._buckets[domain] = (tokens - 1, now)
            return 0.0
        self._buckets[domain] = (tokens, now)
        return (1 - tokens) / rate


class PostgresTokenBucketStore:
    """A Postgres-backed bucket store shared by every worker (one budget per domain)."""

    _CREATE = """
    CREATE TABLE IF NOT EXISTS rate_limit_buckets (
        domain     TEXT PRIMARY KEY,
        tokens     DOUBLE PRECISION NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """

    def __init__(self, dsn: str, connect: Any = None) -> None:
        """Stores the DSN; `connect` is an injectable async-connection factory."""
        self._dsn = dsn
        self._connect = connect
        self._ready = False
        self._ensure_lock = asyncio.Lock()

    async def try_acquire(self, domain: str, rate: float, burst: float) -> float:
        """Atomically refills and decrements the domain's row in one transaction."""
        conn = await self._conn()
        try:
            await self._ensure(conn)
            async with conn.cursor() as cur:
                # lock (or create) the row, then refill by elapsed time
                await cur.execute(
                    """
                    INSERT INTO rate_limit_buckets (domain, tokens) VALUES (%s, %s)
                    ON CONFLICT (domain) DO NOTHING
                    """,
                    (domain, burst),
                )
                await cur.execute(
                    "SELECT tokens, extract(epoch FROM now() - updated_at) "
                    "FROM rate_limit_buckets WHERE domain = %s FOR UPDATE",
                    (domain,),
                )
                row = await cur.fetchone()
                tokens = min(burst, float(row[0]) + float(row[1]) * rate)
                if tokens >= 1:
                    await cur.execute(
                        "UPDATE rate_limit_buckets SET tokens = %s, updated_at = now() "
                        "WHERE domain = %s",
                        (tokens - 1, domain),
                    )
                    await conn.commit()
                    return 0.0
                await cur.execute(
                    "UPDATE rate_limit_buckets SET tokens = %s, updated_at = now() "
                    "WHERE domain = %s",
                    (tokens, domain),
                )
                await conn.commit()
                return (1 - tokens) / rate
        finally:
            await conn.close()

    async def _conn(self) -> Any:
        """Opens a connection via the injected factory or psycopg by default."""
        if self._connect is not None:
            return await self._connect(self._dsn)
        import psycopg

        return await psycopg.AsyncConnection.connect(self._dsn)

    async def _ensure(self, conn: Any) -> None:
        """Creates the bucket table once, serialized and race-tolerant (concurrent
        CREATE TABLE IF NOT EXISTS can still collide in Postgres)."""
        if self._ready:
            return
        async with self._ensure_lock:
            if self._ready:
                return
            try:
                async with conn.cursor() as cur:
                    await cur.execute(self._CREATE)
                await conn.commit()
            except Exception:  # noqa: BLE001 — another worker created it first; fine
                await conn.rollback()
            self._ready = True

"""Checkpoint stores for incremental scraping (plan2.md §16, Plan 09).

Completes the Plan-03 `CheckpointStore` contract: an in-memory store for tests
and a Postgres-backed one so checkpoints survive restarts and are shared across
workers. A checkpoint records where a source left off (cursor, watermark) and the
content hash used to skip unchanged pages.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.models.checkpoint import Checkpoint


class InMemoryCheckpointStore:
    """Process-local checkpoints — fine for tests and single runs, lost on restart."""

    def __init__(self) -> None:
        """Starts with no checkpoints."""
        self._store: dict[str, Checkpoint] = {}

    def get(self, source: str) -> Checkpoint | None:
        """Returns the saved checkpoint for a source, or None."""
        return self._store.get(source)

    def put(self, checkpoint: Checkpoint) -> None:
        """Saves the newest checkpoint for a source."""
        self._store[checkpoint.source] = checkpoint


class PostgresCheckpointStore:
    """Postgres-backed checkpoints so incremental state survives restarts/workers."""

    _CREATE = """
    CREATE TABLE IF NOT EXISTS scraper_checkpoints (
        source       TEXT PRIMARY KEY,
        cursor       TEXT,
        watermark    TIMESTAMPTZ,
        content_hash TEXT,
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """

    def __init__(self, dsn: str, connect: Any = None) -> None:
        """Stores the DSN; `connect` is an injectable sync-connection factory."""
        self._dsn = dsn
        self._connect = connect
        self._ready = False

    def get(self, source: str) -> Checkpoint | None:
        """Loads a source's checkpoint row, or None if it never ran."""
        conn = self._conn()
        try:
            self._ensure(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT source, cursor, watermark, content_hash, updated_at "
                    "FROM scraper_checkpoints WHERE source = %s",
                    (source,),
                )
                row = cur.fetchone()
            if row is None:
                return None
            return Checkpoint(
                source=row[0], cursor=row[1], watermark=row[2],
                content_hash=row[3], updated_at=row[4] or datetime.now(UTC),
            )
        finally:
            conn.close()

    def put(self, checkpoint: Checkpoint) -> None:
        """Upserts a source's checkpoint."""
        conn = self._conn()
        try:
            self._ensure(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scraper_checkpoints
                        (source, cursor, watermark, content_hash, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (source) DO UPDATE SET
                        cursor = EXCLUDED.cursor,
                        watermark = EXCLUDED.watermark,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = now()
                    """,
                    (checkpoint.source, checkpoint.cursor, checkpoint.watermark,
                     checkpoint.content_hash),
                )
            conn.commit()
        finally:
            conn.close()

    def _conn(self) -> Any:
        """Opens a sync connection via the injected factory or psycopg by default."""
        if self._connect is not None:
            return self._connect(self._dsn)
        import psycopg

        return psycopg.connect(self._dsn)

    def _ensure(self, conn: Any) -> None:
        """Creates the checkpoint table once."""
        if self._ready:
            return
        with conn.cursor() as cur:
            cur.execute(self._CREATE)
        conn.commit()
        self._ready = True

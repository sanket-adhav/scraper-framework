"""Pluggable "have I seen this key?" backends for the duplicate detector.

In-memory now and a Postgres-table store for cross-run dedup; a Redis backend
slots in at Plan 09 behind the same tiny contract. Kept synchronous so the
Validator contract stays sync.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SeenStore(Protocol):
    """Records keys and reports whether one was already recorded."""

    def check_and_add(self, key: str) -> bool:
        """Returns True if the key is new (and records it), False if already seen."""
        ...


class InMemorySeenStore:
    """A process-local seen-set — fine for a single run, lost on restart."""

    def __init__(self) -> None:
        """Starts with an empty key set."""
        self._seen: set[str] = set()

    def check_and_add(self, key: str) -> bool:
        """Adds the key, returning whether it was new."""
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


class PostgresSeenStore:
    """A Postgres-backed seen-set so duplicates are caught across runs and workers."""

    def __init__(self, dsn: str, table: str = "seen_keys", connect: object = None) -> None:
        """Stores the DSN and table; `connect` is an injectable sync-connection factory."""
        self._dsn = dsn
        self._table = table
        self._connect = connect
        self._ready = False

    def check_and_add(self, key: str) -> bool:
        """Inserts the key; a fresh insert means new, a conflict means duplicate."""
        conn = self._connection()
        self._ensure_table(conn)
        with conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(
                f"INSERT INTO {self._table} (key) VALUES (%s) ON CONFLICT DO NOTHING", (key,)
            )
            inserted = bool(cur.rowcount == 1)
        conn.commit()  # type: ignore[attr-defined]
        return inserted

    def _ensure_table(self, conn: object) -> None:
        """Creates the seen-keys table once."""
        if self._ready:
            return
        with conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(f"CREATE TABLE IF NOT EXISTS {self._table} (key TEXT PRIMARY KEY)")
        conn.commit()  # type: ignore[attr-defined]
        self._ready = True

    def _connection(self) -> object:
        """Opens a sync connection via the injected factory or psycopg by default."""
        if self._connect is not None:
            return self._connect(self._dsn)  # type: ignore[operator]
        import psycopg

        return psycopg.connect(self._dsn)

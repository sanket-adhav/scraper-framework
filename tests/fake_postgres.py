"""Minimal fake psycopg async/sync connections for unit-testing the Postgres
components without a running database. Real behavior is covered by the
DATABASE_URL-gated contract test that runs against real Postgres in CI."""

from __future__ import annotations

from typing import Any


class FakeAsyncCursor:
    """Records executed SQL; execute is a no-op that can be told to raise."""

    def __init__(self, log: list[tuple[str, Any]], raise_on: Exception | None) -> None:
        """Holds the shared SQL log and an optional error to raise on execute."""
        self._log = log
        self._raise_on = raise_on
        self.rowcount = 1

    async def __aenter__(self) -> FakeAsyncCursor:
        """Enters the cursor context."""
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Exits the cursor context."""

    async def execute(self, sql: str, params: Any = None) -> None:
        """Records the statement, or raises the configured driver error."""
        if self._raise_on is not None:
            raise self._raise_on
        self._log.append((sql, params))


class FakeAsyncConnection:
    """A fake async connection that mints fake cursors and records commits."""

    def __init__(self, raise_on: Exception | None = None) -> None:
        """Starts with an empty SQL log and optional injected driver error."""
        self.log: list[tuple[str, Any]] = []
        self.commits = 0
        self._raise_on = raise_on

    def cursor(self) -> FakeAsyncCursor:
        """Returns a fake cursor sharing this connection's log."""
        return FakeAsyncCursor(self.log, self._raise_on)

    async def commit(self) -> None:
        """Counts a commit."""
        self.commits += 1


def async_connect_factory(conn: FakeAsyncConnection):
    """Returns an async `connect(dsn)` that yields the given fake connection."""

    async def connect(dsn: str) -> FakeAsyncConnection:
        """Async no-op returning the pre-built fake connection."""
        return conn

    return connect


class FakeSyncCursor:
    """A fake sync cursor recording SQL, with a settable rowcount for dedup tests."""

    def __init__(self, seen: set[str]) -> None:
        """Shares the seen-key set so ON CONFLICT DO NOTHING can be simulated."""
        self._seen = seen
        self.rowcount = 0

    def __enter__(self) -> FakeSyncCursor:
        """Enters the cursor context."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Exits the cursor context."""

    def execute(self, sql: str, params: Any = None) -> None:
        """Simulates CREATE TABLE (no-op) and INSERT ... ON CONFLICT DO NOTHING."""
        if sql.strip().upper().startswith("INSERT") and params:
            key = params[0]
            self.rowcount = 0 if key in self._seen else 1
            self._seen.add(key)


class FakeSyncConnection:
    """A fake sync connection for the Postgres seen-store."""

    def __init__(self, seen: set[str]) -> None:
        """Shares a seen-key set across cursors from this connection."""
        self._seen = seen
        self.commits = 0

    def cursor(self) -> FakeSyncCursor:
        """Returns a fake sync cursor."""
        return FakeSyncCursor(self._seen)

    def commit(self) -> None:
        """Counts a commit."""
        self.commits += 1

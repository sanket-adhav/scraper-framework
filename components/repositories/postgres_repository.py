"""PostgreSQL repository (plan2.md §10, Plan 08) — Postgres only for now;
Mongo/Elasticsearch/Kafka are deliberately deferred to later plans.

Upsert-by-key, schema-versioned TEXT columns (old and new record shapes coexist),
and lightweight auto-migration (ADD COLUMN) when a spec grows a field. A
driver-level connection failure maps to a transient PersistError (retryable); a
data/constraint problem maps to permanent (quarantine).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from components.repositories._postgres_sql import (
    add_column_sql,
    create_table_sql,
    insert_sql,
    safe_identifier,
    unique_index_sql,
)
from components.repositories._rows import record_to_row
from core.errors.exceptions import PersistError
from core.models.record import Record


class PostgresRepository:
    """Saves records into a Postgres table, creating/migrating it as fields appear."""

    def __init__(
        self,
        dsn: str,
        table: str,
        mode: str = "upsert",
        key_fields: Sequence[str] = (),
        connect: object = None,
    ) -> None:
        """Stores the connection string, target table, write mode, and key fields.
        `connect` is an injectable async-connection factory for tests."""
        if mode not in ("append", "upsert"):
            raise ValueError(f"mode must be 'append' or 'upsert', got {mode!r}")
        if mode == "upsert" and not key_fields:
            raise ValueError("upsert mode needs key_fields")
        self._dsn = dsn
        self._table = safe_identifier(table)
        self._mode = mode
        self._key_fields = list(key_fields)
        self._connect = connect
        self._known_columns: set[str] = set()
        self._table_ready = False

    async def save(self, record: Record) -> None:
        """Writes one record, creating the table and adding new columns on demand."""
        row = {k: _stringify(v) for k, v in record_to_row(record).items()}
        columns = list(row.keys())
        try:
            conn = await self._connection()
            async with conn.cursor() as cur:
                await self._ensure_schema(cur, columns)
                key_fields = self._key_fields if self._mode == "upsert" else []
                await cur.execute(insert_sql(self._table, columns, key_fields), list(row.values()))
            await conn.commit()
        except Exception as err:  # noqa: BLE001 — classify, then re-raise as a typed error
            raise _classify(err) from err

    async def _ensure_schema(self, cur: Any, columns: Sequence[str]) -> None:
        """Creates the table once, then adds any columns this record introduced."""
        execute = cur.execute
        if not self._table_ready:
            await execute(create_table_sql(self._table, columns))
            if self._mode == "upsert":
                await execute(unique_index_sql(self._table, self._key_fields))
            self._known_columns = set(columns)
            self._table_ready = True
            return
        for new_col in [c for c in columns if c not in self._known_columns]:
            await execute(add_column_sql(self._table, new_col))
            self._known_columns.add(new_col)

    async def _connection(self) -> Any:
        """Opens a connection via the injected factory, or psycopg by default."""
        if self._connect is not None:
            return await self._connect(self._dsn)  # type: ignore[operator]
        import psycopg

        return await psycopg.AsyncConnection.connect(self._dsn)


def _stringify(value: object) -> str | None:
    """Renders a value as text for a TEXT column (None stays NULL)."""
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _classify(err: Exception) -> PersistError:
    """Maps a driver error to transient (retry) vs permanent (quarantine)."""
    name = type(err).__name__
    transient_markers = ("OperationalError", "InterfaceError", "ConnectionError", "PoolTimeout")
    transient = any(marker in name for marker in transient_markers)
    return PersistError(f"postgres save failed ({name}): {err}", transient=transient)

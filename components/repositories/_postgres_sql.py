"""Pure SQL builders for the Postgres repository — no driver, no I/O.

Kept separate so the SQL logic (DDL, upsert vs append, provenance columns) is
unit-tested without a running database; the repository just executes what these
return.
"""

from __future__ import annotations

from collections.abc import Sequence

from components.repositories._rows import PROVENANCE_COLUMNS

_IDENT_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def safe_identifier(name: str) -> str:
    """Validates a table/column name (letters, digits, underscore) to prevent injection."""
    if not name or name[0].isdigit() or any(c not in _IDENT_OK for c in name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


def create_table_sql(table: str, data_columns: Sequence[str]) -> str:
    """Builds CREATE TABLE IF NOT EXISTS with data columns plus provenance columns.
    Every column is TEXT — schema-versioned rows keep old and new shapes side by side."""
    safe_table = safe_identifier(table)
    cols = [f"{safe_identifier(c)} TEXT" for c in data_columns]
    cols += [f"{safe_identifier(c)} TEXT" for c in PROVENANCE_COLUMNS if c not in data_columns]
    return f"CREATE TABLE IF NOT EXISTS {safe_table} ({', '.join(cols)})"


def add_column_sql(table: str, column: str) -> str:
    """Builds ADD COLUMN IF NOT EXISTS — the lightweight migration for spec drift."""
    col = safe_identifier(column)
    return f"ALTER TABLE {safe_identifier(table)} ADD COLUMN IF NOT EXISTS {col} TEXT"


def insert_sql(table: str, columns: Sequence[str], key_fields: Sequence[str]) -> str:
    """Builds a parameterized INSERT; upsert (ON CONFLICT) when key_fields are given.
    Values are passed as parameters, never interpolated — only identifiers are inlined."""
    safe_table = safe_identifier(table)
    safe_cols = [safe_identifier(c) for c in columns]
    placeholders = ", ".join(["%s"] * len(safe_cols))
    stmt = f"INSERT INTO {safe_table} ({', '.join(safe_cols)}) VALUES ({placeholders})"
    if not key_fields:
        return stmt
    safe_keys = [safe_identifier(k) for k in key_fields]
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in safe_cols if c not in safe_keys)
    conflict = ", ".join(safe_keys)
    if not updates:  # all columns are keys — nothing to update on conflict
        return f"{stmt} ON CONFLICT ({conflict}) DO NOTHING"
    return f"{stmt} ON CONFLICT ({conflict}) DO UPDATE SET {updates}"


def unique_index_sql(table: str, key_fields: Sequence[str]) -> str:
    """Builds the unique index the upsert's ON CONFLICT target requires."""
    safe_table = safe_identifier(table)
    safe_keys = [safe_identifier(k) for k in key_fields]
    index = safe_identifier(f"{table}_key_uidx")
    return f"CREATE UNIQUE INDEX IF NOT EXISTS {index} ON {safe_table} ({', '.join(safe_keys)})"

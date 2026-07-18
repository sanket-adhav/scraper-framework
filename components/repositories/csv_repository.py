"""Repository that writes records to a CSV file, appending or upserting by key."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from components.repositories._rows import record_to_row, row_key
from core.errors.exceptions import PersistError
from core.models.record import Record


class CsvRepository:
    """Saves records as CSV rows with schema_version + provenance columns.
    mode 'append' adds every record; 'upsert' replaces the row with the same key."""

    def __init__(
        self, path: str | Path, mode: str = "append", key_fields: Sequence[str] = ()
    ) -> None:
        """Remembers the file path, write mode, and (for upsert) the key fields."""
        if mode not in ("append", "upsert"):
            raise ValueError(f"mode must be 'append' or 'upsert', got {mode!r}")
        if mode == "upsert" and not key_fields:
            raise ValueError("upsert mode needs key_fields")
        self._path = Path(path)
        self._mode = mode
        self._key_fields = list(key_fields)

    async def save(self, record: Record) -> None:
        """Writes one record to the CSV file per the configured mode."""
        try:
            row = record_to_row(record)
            rows = self._read_rows()
            if self._mode == "upsert":
                key = row_key(row, self._key_fields)
                rows = [r for r in rows if row_key(r, self._key_fields) != key]
            rows.append(row)
            self._write_rows(rows)
        except OSError as err:
            raise PersistError(f"CSV write failed: {err}", transient=True) from err

    def _read_rows(self) -> list[dict[str, Any]]:
        """Loads the existing rows (empty if the file doesn't exist yet)."""
        if not self._path.exists():
            return []
        with self._path.open(newline="", encoding="utf-8") as f:
            return [dict(r) for r in csv.DictReader(f)]

    def _write_rows(self, rows: list[dict[str, Any]]) -> None:
        """Rewrites the whole file with a header covering every column seen."""
        columns: list[str] = []
        for row in rows:
            for name in row:
                if name not in columns:
                    columns.append(name)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

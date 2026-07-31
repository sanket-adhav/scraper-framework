"""Repository that writes records to a formatted JSON file (JSON Array with indentation)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from components.repositories._rows import record_to_row, row_key
from core.errors.exceptions import PersistError
from core.models.record import Record


class JsonRepository:
    """Saves records as a pretty-formatted JSON array, with schema_version + provenance.
    mode 'append' adds every record; 'upsert' replaces the record with the same key."""

    def __init__(
        self,
        path: str | Path,
        mode: str = "upsert",
        key_fields: Sequence[str] = (),
        indent: int = 2,
    ) -> None:
        """Remembers the file path, write mode, key fields, and indentation."""
        if mode not in ("append", "upsert"):
            raise ValueError(f"mode must be 'append' or 'upsert', got {mode!r}")
        if mode == "upsert" and not key_fields:
            raise ValueError("upsert mode needs key_fields")
        self._path = Path(path)
        self._mode = mode
        self._key_fields = list(key_fields)
        self._indent = indent

    async def save(self, record: Record) -> None:
        """Writes one record per the configured mode into a formatted JSON array."""
        try:
            row = record_to_row(record)
            rows = self._read_rows()

            if self._mode == "upsert":
                key = row_key(row, self._key_fields)
                rows = [r for r in rows if row_key(r, self._key_fields) != key]

            rows.append(row)

            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, default=str, indent=self._indent)
                f.write("\n")
        except OSError as err:
            raise PersistError(f"JSON write failed: {err}", transient=True) from err

    def _read_rows(self) -> list[dict[str, Any]]:
        """Loads existing JSON array (empty if the file doesn't exist yet)."""
        if not self._path.exists():
            return []
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

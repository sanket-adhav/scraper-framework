"""Repository that writes records as JSON lines, appending or upserting by key."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from components.repositories._rows import record_to_row, row_key
from core.errors.exceptions import PersistError
from core.models.record import Record


class JsonlRepository:
    """Saves records as one JSON object per line, with schema_version + provenance.
    mode 'append' adds every record; 'upsert' replaces the line with the same key."""

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
        """Writes one record per the configured mode."""
        try:
            row = record_to_row(record)
            if self._mode == "append":
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                return
            rows = self._read_rows()
            key = row_key(row, self._key_fields)
            rows = [r for r in rows if row_key(r, self._key_fields) != key]
            rows.append(row)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        except OSError as err:
            raise PersistError(f"JSONL write failed: {err}", transient=True) from err

    def _read_rows(self) -> list[dict[str, Any]]:
        """Loads existing lines (empty if the file doesn't exist yet)."""
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

"""File-based quarantine sink: appends failed-scrape snapshots to a JSONL file."""

from __future__ import annotations

import json
from pathlib import Path

from core.errors.quarantine import QuarantineRecord


class FileQuarantineSink:
    """Writes each quarantine record as one JSON line in a needs-review file."""

    def __init__(self, directory: str | Path) -> None:
        """Creates the quarantine directory if needed and points at quarantine.jsonl."""
        self._path = Path(directory) / "quarantine.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def put(self, record: QuarantineRecord) -> None:
        """Appends one record to the file so nothing needing review is ever lost."""
        line = json.dumps(
            {
                "trace_id": record.trace_id,
                "stage": record.stage,
                "error_type": record.error_type,
                "error_message": record.error_message,
                "context_snapshot": dict(record.context_snapshot),
                "quarantined_at": record.quarantined_at.isoformat(),
            },
            ensure_ascii=False,
            default=str,
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_all(self) -> list[dict[str, object]]:
        """Reads back all quarantined records (for the `scraper quarantine` CLI)."""
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def discard_all(self) -> int:
        """Clears the needs-review pile after the operator has dealt with it."""
        records = self.read_all()
        self._path.write_text("", encoding="utf-8")
        return len(records)

    def rewrite(self, records: list[dict[str, object]]) -> None:
        """Replaces the pile with the given records (used by selective retry/discard)."""
        with self._path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

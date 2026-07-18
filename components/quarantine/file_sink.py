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

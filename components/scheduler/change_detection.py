"""Content-hash change detection + re-scrape policy for incremental scraping (Plan 09).

Skip-unchanged: hash a source's content and compare to its last checkpoint; an
unchanged hash means nothing to re-scrape, so children aren't fetched — the DoD's
"near-zero fetching on an unchanged corpus". A per-plugin re-scrape policy decides
when a source is due again (age-based) or forced.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from core.contracts.checkpoint_store import CheckpointStore
from core.models.checkpoint import Checkpoint


class ChangeDetector:
    """Decides whether a source's content changed since its last checkpoint."""

    def __init__(self, store: CheckpointStore) -> None:
        """Remembers the checkpoint store that holds each source's last hash."""
        self._store = store

    def changed(self, source: str, content: bytes, *, cursor: str | None = None) -> bool:
        """Hashes the content; returns True if new/changed (and records the hash),
        False if identical to the last run (skip it)."""
        digest = hashlib.sha256(content).hexdigest()
        previous = self._store.get(source)
        if previous is not None and previous.content_hash == digest:
            return False
        self._store.put(
            Checkpoint(
                source=source,
                cursor=cursor if cursor is not None else (previous.cursor if previous else None),
                content_hash=digest,
                updated_at=datetime.now(UTC),
            )
        )
        return True


def is_due(
    checkpoint: Checkpoint | None,
    now: datetime,
    *,
    min_age_seconds: float,
    forced: bool = False,
) -> bool:
    """Returns whether a source should be re-scraped: forced, never-run, or older
    than its configured re-scrape age."""
    if forced or checkpoint is None:
        return True
    return (now - checkpoint.updated_at).total_seconds() >= min_age_seconds

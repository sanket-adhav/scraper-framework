"""CheckpointStore contract — saves/loads per-source incremental checkpoints (Plan 09)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.models.checkpoint import Checkpoint

__all__ = ["Checkpoint", "CheckpointStore"]


@runtime_checkable
class CheckpointStore(Protocol):
    """Anything that can save and load per-source checkpoints."""

    def get(self, source: str) -> Checkpoint | None:
        """Returns the last checkpoint for a source, or None if it never ran."""
        ...

    def put(self, checkpoint: Checkpoint) -> None:
        """Saves the newest checkpoint for a source."""
        ...

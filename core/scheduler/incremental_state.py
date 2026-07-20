"""Incremental-scraping state (plan2.md §16).

Checkpoint (a model) and CheckpointStore (a contract) moved to core/models and
core/contracts so components may import them without crossing the boundary.
Re-exported here for anything that referenced the old location.
"""

from __future__ import annotations

from core.contracts.checkpoint_store import CheckpointStore
from core.models.checkpoint import Checkpoint

__all__ = ["Checkpoint", "CheckpointStore"]

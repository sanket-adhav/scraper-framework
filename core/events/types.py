"""Event names and the Event envelope the pipeline emits (plan2.md §10).

The full async bus arrives in Plan 08; the names are fixed now so instrumented
code never has to change.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

JOB_STARTED = "job.started"
JOB_COMPLETED = "job.completed"
JOB_FAILED = "job.failed"
STAGE_STARTED = "stage.started"
STAGE_COMPLETED = "stage.completed"
STAGE_FAILED = "stage.failed"
STAGE_RETRYING = "stage.retrying"
RECORD_QUARANTINED = "record.quarantined"


@dataclass(frozen=True, slots=True)
class Event:
    """One thing that happened, with a name, a payload, and a timestamp."""

    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

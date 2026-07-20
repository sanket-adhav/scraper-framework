"""Event names and the Event envelope the pipeline emits (plan2.md §10).

The full event set from §10, fixed so instrumented code and listeners never
have to change as the system grows.
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
RECORD_EXTRACTED = "record.extracted"
RECORD_SAVED = "record.saved"
RECORD_QUARANTINED = "record.quarantined"
VALIDATION_FAILED = "validation.failed"
FETCH_RETRYING = "fetch.retrying"
CIRCUIT_OPENED = "circuit.opened"
CIRCUIT_CLOSED = "circuit.closed"
BLOCK_DETECTED = "block.detected"
PLUGIN_QUARANTINED = "plugin.quarantined"
COST_TICK = "cost.tick"


@dataclass(frozen=True, slots=True)
class Event:
    """One thing that happened, with a name, a payload, and a timestamp."""

    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

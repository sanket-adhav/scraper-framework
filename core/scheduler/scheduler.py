"""Scheduler interface stub — real cron/event scheduling arrives in Plan 09."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from core.models.job import ScrapeJob


@runtime_checkable
class Scheduler(Protocol):
    """Anything that can decide which jobs are due to run at a given time."""

    def due_jobs(self, now: datetime) -> Sequence[ScrapeJob]:
        """Returns the jobs that should be submitted now."""
        ...

"""Stage contract — the one shape everything in the pipeline has (plan2.md §4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from core.errors.exceptions import ScraperError


class ErrorAction(StrEnum):
    """What the pipeline runner does when a stage fails (plan2.md §4, §10)."""

    RETRY = "retry"
    SKIP = "skip"
    QUARANTINE = "quarantine"
    ABORT = "abort"


@runtime_checkable
class Context(Protocol):
    """The pipeline's data carrier. The concrete carrier (request, response,
    document, record, discovered_requests, resolved config) is built in Plan 03
    at core/pipeline/context.py; stages depend only on this surface."""

    trace_id: str


@runtime_checkable
class Stage(Protocol):
    name: str

    async def run(self, ctx: Context) -> Context: ...

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction: ...

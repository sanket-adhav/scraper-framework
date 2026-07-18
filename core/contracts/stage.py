"""Stage contract — the one shape everything in the pipeline has (plan2.md §4)."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from core.contracts.document import Document
from core.contracts.validator import ValidationResult
from core.errors.exceptions import ScraperError
from core.models.record import Record
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


class ErrorAction(StrEnum):
    """What the pipeline runner does when a stage fails (plan2.md §4, §10)."""

    RETRY = "retry"
    SKIP = "skip"
    QUARANTINE = "quarantine"
    ABORT = "abort"


@runtime_checkable
class Context(Protocol):
    """The pipeline data carrier's surface, as stages see it. The concrete
    carrier lives in core/pipeline/context.py; stages (which live in
    components/ and may not import core.pipeline) depend only on this shape."""

    trace_id: str
    config: Mapping[str, Any]
    config_fingerprint: str
    request: ScrapeRequest | None
    response: Response | None
    document: Document | None
    record: Record | None
    validation_result: ValidationResult | None
    discovered_requests: list[ScrapeRequest]


@runtime_checkable
class Stage(Protocol):
    name: str

    async def run(self, ctx: Context) -> Context: ...

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction: ...

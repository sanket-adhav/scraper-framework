"""The Context — the work-in-progress data carrier passed stage to stage (plan2.md §4).

Pure data, no logic. Each stage reads what it needs and fills in what it
produced; discovered requests flow back to the engine for follow-up scraping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.contracts.document import Document
from core.contracts.validator import ValidationResult
from core.models.record import Record
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


@dataclass(slots=True)
class Context:
    """Everything known about one scrape as it moves through the pipeline."""

    trace_id: str
    config: Mapping[str, Any]
    config_fingerprint: str
    request: ScrapeRequest | None = None
    response: Response | None = None
    document: Document | None = None
    record: Record | None = None
    validation_result: ValidationResult | None = None
    discovered_requests: list[ScrapeRequest] = field(default_factory=list)

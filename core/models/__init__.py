"""Plain, frozen data models — no behavior lives here (plan2.md §8)."""

from core.models.record import Provenance, Record
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest, ScrapeRequestBuilder
from core.models.selector import Selector, SelectorKind

__all__ = [
    "Provenance",
    "Record",
    "Response",
    "ScrapeRequest",
    "ScrapeRequestBuilder",
    "Selector",
    "SelectorKind",
]

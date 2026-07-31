"""Parser contract — turns a Response into a Document (plan2.md §3, §5)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.contracts.document import Document
from core.errors.exceptions import ParseError
from core.models.response import Response

__all__ = ["ParseError", "Parser"]


@runtime_checkable
class Parser(Protocol):
    content_types: frozenset[str]
    """Content types this parser accepts, e.g. {"text/html"}."""

    document_type: type
    """The Document class this parser produces. The load-time capability check
    (plan2.md §5) reads this class's `capabilities` to validate extraction
    specs before any scrape starts. See docs/adr/0001."""

    def parse(self, response: Response) -> Document: ...

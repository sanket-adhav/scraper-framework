"""Parser contract — turns a Response into a Document (plan2.md §3, §5)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.contracts.document import Document
from core.errors.exceptions import ScraperError
from core.models.response import Response


class ParseError(ScraperError):
    """The body could not be parsed into the declared document type."""


@runtime_checkable
class Parser(Protocol):
    content_types: frozenset[str]
    """Content types this parser accepts, e.g. {"text/html"}."""

    def parse(self, response: Response) -> Document: ...

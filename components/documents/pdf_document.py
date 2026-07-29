"""PDF content as a Document: query its extracted text with regex or read it whole (plan2.md §5).
# stores pdf data 
Positional block data is kept per page so layout-aware selectors can be added
later without re-parsing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from components.documents._shared import regex_select, require_capability
from core.models.selector import Selector, SelectorKind


@dataclass(frozen=True, slots=True)
class PdfBlock:
    """One block of text on a page with its bounding-box coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True, slots=True)
class PdfPage:
    """The text of one PDF page plus the positioned blocks it came from."""

    number: int
    text: str
    blocks: tuple[PdfBlock, ...]


class PdfDocument:
    """Holds text extracted from a PDF (page by page) and answers text/regex queries on it."""

    capabilities: ClassVar[frozenset[SelectorKind]] = frozenset(
        {SelectorKind.TEXT, SelectorKind.REGEX}
    )

    def __init__(self, pages: tuple[PdfPage, ...], raw: bytes, content_type: str) -> None:
        """Stores the extracted pages, the original bytes, and the content type."""
        self.pages = pages
        self._raw = raw
        self.content_type = content_type

    def select(self, selector: Selector) -> list[str | Mapping[str, Any]]:
        """Runs one selector query over the extracted text and returns plain strings."""
        require_capability(self.capabilities, selector.kind, type(self).__name__)
        if selector.kind is SelectorKind.REGEX:
            return regex_select(self.text(), selector.query)
        return [self.text()]

    def text(self) -> str:
        """Returns the text of all pages joined into one string."""
        return "\n".join(page.text for page in self.pages)

    def raw(self) -> bytes:
        """Returns the original PDF bytes, untouched."""
        return self._raw

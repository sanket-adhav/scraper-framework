"""Plain text as a Document: the fallback for text/plain responses (plan2.md §5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from components.documents._shared import regex_select, require_capability
from core.models.selector import Selector, SelectorKind


class TextDocument:
    """Holds plain text and answers text/regex queries on it."""

    capabilities: ClassVar[frozenset[SelectorKind]] = frozenset(
        {SelectorKind.TEXT, SelectorKind.REGEX}
    )

    def __init__(self, content: str, raw: bytes, content_type: str) -> None:
        """Stores the decoded text, the original bytes, and the content type."""
        self._content = content
        self._raw = raw
        self.content_type = content_type

    def select(self, selector: Selector) -> list[str | Mapping[str, Any]]:
        """Runs one selector query over the text and returns plain strings."""
        require_capability(self.capabilities, selector.kind, type(self).__name__)
        if selector.kind is SelectorKind.REGEX:
            return regex_select(self._content, selector.query)
        return [self._content]

    def text(self) -> str:
        """Returns the whole text as one string."""
        return self._content

    def raw(self) -> bytes:
        """Returns the original response body, untouched."""
        return self._raw

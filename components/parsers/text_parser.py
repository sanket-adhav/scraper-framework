"""Parser that turns a plain-text response into a TextDocument."""

from __future__ import annotations

from typing import ClassVar

from components.documents.text_document import TextDocument
from components.parsers._hardening import DEFAULT_MAX_BODY_BYTES, checked_body
from core.models.response import Response


class TextParser:
    """Reads a plain-text response body and produces a queryable TextDocument."""

    content_types: ClassVar[frozenset[str]] = frozenset({"text/plain"})
    document_type: ClassVar[type[TextDocument]] = TextDocument

    def __init__(self, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        """Remembers the body size limit this parser will enforce."""
        self._max_body_bytes = max_body_bytes

    def parse(self, response: Response) -> TextDocument:
        """Checks safety limits, decodes the bytes as UTF-8, and returns a TextDocument."""
        body = checked_body(response, self._max_body_bytes)
        content = body.decode("utf-8", errors="replace")
        return TextDocument(content, body, response.content_type or "text/plain")

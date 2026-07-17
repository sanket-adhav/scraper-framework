"""Parser that turns an HTML response into an HtmlDocument."""

from __future__ import annotations

from typing import ClassVar

from lxml import html as lxml_html

from components.documents.html_document import HtmlDocument
from components.parsers._hardening import DEFAULT_MAX_BODY_BYTES, checked_body
from core.contracts.parser import ParseError
from core.models.response import Response


class HtmlParser:
    """Reads an HTML response body and produces a queryable HtmlDocument."""

    content_types: ClassVar[frozenset[str]] = frozenset({"text/html", "application/xhtml+xml"})
    document_type: ClassVar[type[HtmlDocument]] = HtmlDocument

    def __init__(self, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        """Remembers the body size limit this parser will enforce."""
        self._max_body_bytes = max_body_bytes

    def parse(self, response: Response) -> HtmlDocument:
        """Checks safety limits, parses the HTML, and returns an HtmlDocument."""
        body = checked_body(response, self._max_body_bytes)
        try:
            root = lxml_html.fromstring(body)
        except Exception as err:
            raise ParseError(f"could not parse HTML: {err}") from err
        return HtmlDocument(root, body, response.content_type or "text/html")

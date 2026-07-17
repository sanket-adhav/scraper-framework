"""Parser that turns a PDF response into a PdfDocument with per-page text and block positions."""

from __future__ import annotations

from typing import Any, ClassVar

import pymupdf

from components.documents.pdf_document import PdfBlock, PdfDocument, PdfPage
from components.parsers._hardening import DEFAULT_MAX_BODY_BYTES, checked_body
from core.contracts.parser import ParseError
from core.models.response import Response


class PdfParser:
    """Reads a PDF response body and produces a queryable PdfDocument."""

    content_types: ClassVar[frozenset[str]] = frozenset({"application/pdf"})
    document_type: ClassVar[type[PdfDocument]] = PdfDocument

    def __init__(self, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        """Remembers the body size limit this parser will enforce."""
        self._max_body_bytes = max_body_bytes

    def parse(self, response: Response) -> PdfDocument:
        """Checks safety limits, extracts text and blocks per page, returns a PdfDocument."""
        body = checked_body(response, self._max_body_bytes)
        try:
            pdf = pymupdf.open(stream=body, filetype="pdf")
        except Exception as err:
            raise ParseError(f"could not parse PDF: {err}") from err
        try:
            pages = tuple(_extract_page(pdf[i], i + 1) for i in range(pdf.page_count))
        finally:
            pdf.close()
        return PdfDocument(pages, body, response.content_type or "application/pdf")


def _extract_page(page: Any, number: int) -> PdfPage:
    """Pulls the plain text and the positioned text blocks out of one PDF page."""
    blocks = tuple(
        PdfBlock(x0=b[0], y0=b[1], x1=b[2], y1=b[3], text=b[4].strip())
        for b in page.get_text("blocks")
        if b[6] == 0  # text blocks only, skip images
    )
    return PdfPage(number=number, text=page.get_text().strip(), blocks=blocks)

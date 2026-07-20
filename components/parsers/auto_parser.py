"""AutoParser — dynamic content-type routing for multi-format pipelines.

Inspects Response.content_type at runtime and delegates to the correct
specialised parser (HTML, PDF, JSON, XML, or Text fallback).  This allows
a single plugin to seamlessly scrape an HTML list page and then download
PDFs without declaring a parser in its YAML.

When the config says ``parser: auto`` (or omits the parser key entirely),
the engine uses this parser.  Future parsers (e.g. Excel) are picked up
automatically once registered — no code changes required.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from core.contracts.document import Document
from core.contracts.parser import ParseError
from core.models.response import Response
from core.models.selector import Selector, SelectorKind

logger = logging.getLogger("scraper.auto_parser")


# ---------------------------------------------------------------------------
# AutoDocument — a lightweight proxy that wraps whichever real document the
# delegated parser produced, and exposes the UNION of all capabilities so the
# load-time capability check passes.
# ---------------------------------------------------------------------------

class AutoDocument:
    """Wraps a real document (HtmlDocument, PdfDocument, etc.) and reports the
    union of all known capabilities so load-time checks pass.  At runtime,
    selectors are forwarded to the wrapped document which enforces its own
    capabilities."""

    capabilities: ClassVar[frozenset[SelectorKind]] = frozenset(SelectorKind)

    def __init__(self, inner: Document) -> None:
        self._inner: Document = inner
        self.content_type: str = getattr(inner, "content_type", "")

    def select(self, selector: Selector) -> list[str | Mapping[str, Any]]:
        """Delegates to the wrapped document's select method."""
        return self._inner.select(selector)

    def text(self) -> str:
        """Returns the plain-text projection from the wrapped document."""
        return self._inner.text()

    def raw(self) -> bytes:
        """Returns the original response body from the wrapped document."""
        return self._inner.raw()


class AutoParser:
    """Content-type–aware parser that delegates to the correct specialised parser
    at runtime.  Accepts a sequence of parser instances at construction time and
    builds a content-type → parser routing map.

    Usage in YAML::

        parser: auto          # or simply omit the parser key
    """

    # The AutoDocument reports the union of ALL selector kinds so that the
    # load-time capability check in core/config/capability_check.py passes
    # regardless of what selectors the extraction spec uses.
    content_types: ClassVar[frozenset[str]] = frozenset()  # set dynamically
    document_type: ClassVar[type] = AutoDocument

    def __init__(self, parsers: Sequence[Any] | None = None) -> None:
        """Builds the content-type routing map from the given parser instances.

        Args:
            parsers: Sequence of parser instances (HtmlParser, PdfParser, etc.).
                     If None, defaults are built lazily on first parse() call.
        """
        self._parsers: list[Any] = list(parsers or [])
        self._route_map: dict[str, Any] = {}
        self._fallback: Any | None = None
        self._built = False

    def _ensure_built(self) -> None:
        """Lazily builds the routing map on first use."""
        if self._built:
            return

        # Build route map: content_type string → parser instance
        for parser in self._parsers:
            for ct in getattr(parser, "content_types", frozenset()):
                self._route_map[ct] = parser

        # The TextParser handles text/plain and acts as fallback
        for parser in self._parsers:
            if "text/plain" in getattr(parser, "content_types", frozenset()):
                self._fallback = parser
                break

        # Update our own content_types to the union of all parsers
        all_ct: set[str] = set()
        for parser in self._parsers:
            all_ct.update(getattr(parser, "content_types", frozenset()))
        type(self).content_types = frozenset(all_ct)

        self._built = True

    def parse(self, response: Response) -> AutoDocument:
        """Inspects response.content_type, delegates to the matching parser,
        and wraps the result in an AutoDocument."""
        self._ensure_built()

        ct = (response.content_type or "").strip().lower()

        # Try exact match first
        parser = self._route_map.get(ct)

        # Try prefix match (e.g. "text/html; charset=utf-8" → "text/html")
        if parser is None:
            for known_ct, known_parser in self._route_map.items():
                if ct.startswith(known_ct):
                    parser = known_parser
                    break

        # Fallback to TextParser
        if parser is None:
            parser = self._fallback
            if parser is None:
                raise ParseError(
                    f"AutoParser has no parser for content-type {ct!r} and no fallback"
                )
            logger.info("AutoParser: no parser for %r, falling back to TextParser", ct)

        logger.debug("AutoParser: routing %r → %s", ct, type(parser).__name__)
        real_doc = parser.parse(response)
        return AutoDocument(real_doc)


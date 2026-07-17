"""Parser that turns an XML response into an XmlDocument, with entity-bomb protection."""

from __future__ import annotations

from typing import ClassVar

from lxml import etree

from components.documents.xml_document import XmlDocument
from components.parsers._hardening import (
    DEFAULT_MAX_BODY_BYTES,
    checked_body,
    reject_xml_entity_declarations,
)
from core.contracts.parser import ParseError
from core.models.response import Response


class XmlParser:
    """Reads an XML response body and produces a queryable XmlDocument."""

    content_types: ClassVar[frozenset[str]] = frozenset(
        {"application/xml", "text/xml", "application/rss+xml", "application/atom+xml"}
    )
    document_type: ClassVar[type[XmlDocument]] = XmlDocument

    def __init__(self, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        """Remembers the body size limit and builds a hardened lxml parser."""
        self._max_body_bytes = max_body_bytes
        self._parser = etree.XMLParser(
            resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False
        )

    def parse(self, response: Response) -> XmlDocument:
        """Checks safety limits, rejects entity bombs, parses, and returns an XmlDocument."""
        body = checked_body(response, self._max_body_bytes)
        reject_xml_entity_declarations(body)
        try:
            root = etree.fromstring(body, parser=self._parser)
        except etree.XMLSyntaxError as err:
            raise ParseError(f"could not parse XML: {err}") from err
        return XmlDocument(root, body, response.content_type or "application/xml")

"""XML document as a Document: query it with XPath, regex, or plain text (plan2.md §5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from lxml import etree

from components.documents._shared import regex_select, require_capability
from core.models.selector import Selector, SelectorKind


class XmlDocument:
    """Holds a parsed XML tree and answers XPath/regex/text queries on it."""

    capabilities: ClassVar[frozenset[SelectorKind]] = frozenset(
        {SelectorKind.XPATH, SelectorKind.REGEX, SelectorKind.TEXT}
    )

    def __init__(self, root: etree._Element, raw: bytes, content_type: str) -> None:
        """Stores the parsed lxml tree, the original bytes, and the content type."""
        self._root = root
        self._raw = raw
        self.content_type = content_type

    def select(self, selector: Selector) -> list[str | Mapping[str, Any]]:
        """Runs one selector query and returns every match as a plain string."""
        require_capability(self.capabilities, selector.kind, type(self).__name__)
        if selector.kind is SelectorKind.XPATH:
            result = self._root.xpath(selector.query)
            values = result if isinstance(result, list) else [result]
            return [_node_to_str(v) for v in values]
        if selector.kind is SelectorKind.REGEX:
            return regex_select(self.text(), selector.query)
        return [self.text()]

    def text(self) -> str:
        """Returns all text inside the XML as one string."""
        return "".join(str(t) for t in self._root.itertext())

    def raw(self) -> bytes:
        """Returns the original response body, untouched."""
        return self._raw


def _node_to_str(value: Any) -> str:
    """Converts an XPath match (element, attribute, or scalar) to a plain string."""
    if isinstance(value, etree._Element):
        return "".join(str(t) for t in value.itertext())
    return str(value)

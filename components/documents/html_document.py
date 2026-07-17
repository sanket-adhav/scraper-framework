"""HTML page as a Document: query it with CSS, XPath, regex, or plain text (plan2.md §5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from lxml import html as lxml_html

from components.documents._shared import regex_select, require_capability
from core.models.selector import Selector, SelectorKind


class HtmlDocument:
    """Holds a parsed HTML page and answers CSS/XPath/regex/text queries on it."""

    capabilities: ClassVar[frozenset[SelectorKind]] = frozenset(
        {SelectorKind.CSS, SelectorKind.XPATH, SelectorKind.REGEX, SelectorKind.TEXT}
    )

    def __init__(self, root: lxml_html.HtmlElement, raw: bytes, content_type: str) -> None:
        """Stores the parsed lxml tree, the original bytes, and the content type."""
        self._root = root
        self._raw = raw
        self.content_type = content_type

    def select(self, selector: Selector) -> list[str | Mapping[str, Any]]:
        """Runs one selector query and returns every match as a plain string."""
        require_capability(self.capabilities, selector.kind, type(self).__name__)
        if selector.kind is SelectorKind.CSS:
            return [_node_to_str(el) for el in self._root.cssselect(selector.query)]
        if selector.kind is SelectorKind.XPATH:
            return [_node_to_str(v) for v in _as_list(self._root.xpath(selector.query))]
        if selector.kind is SelectorKind.REGEX:
            return regex_select(self.text(), selector.query)
        return [self.text()]

    def text(self) -> str:
        """Returns the visible text of the whole page as one string."""
        return str(self._root.text_content())

    def raw(self) -> bytes:
        """Returns the original response body, untouched."""
        return self._raw


def _as_list(result: Any) -> list[Any]:
    """Wraps scalar XPath results (like count()) into a list so callers see one shape."""
    return result if isinstance(result, list) else [result]


def _node_to_str(value: Any) -> str:
    """Converts an XPath/CSS match (element, attribute, or scalar) to a plain string."""
    if hasattr(value, "text_content"):
        return str(value.text_content())
    return str(value)

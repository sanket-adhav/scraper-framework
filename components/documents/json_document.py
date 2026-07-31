"""JSON data as a Document: query it with JSONPath, regex, or plain text (plan2.md §5)."""
# stores json data
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar

import jsonpath_ng

from components.documents._shared import regex_select, require_capability
from core.models.selector import Selector, SelectorKind


class JsonDocument:
    """Holds parsed JSON data and answers JSONPath/regex/text queries on it."""

    capabilities: ClassVar[frozenset[SelectorKind]] = frozenset(
        {SelectorKind.JSONPATH, SelectorKind.REGEX, SelectorKind.TEXT}
    )

    def __init__(self, data: Any, raw: bytes, content_type: str) -> None:
        """Stores the parsed JSON value, the original bytes, and the content type."""
        self._data = data
        self._raw = raw
        self.content_type = content_type

    def select(self, selector: Selector) -> list[str | Mapping[str, Any]]:
        """Runs one selector query and returns matches as plain strings or dicts."""
        require_capability(self.capabilities, selector.kind, type(self).__name__)
        if selector.kind is SelectorKind.JSONPATH:
            matches = jsonpath_ng.parse(selector.query).find(self._data)
            return [_value_to_plain(m.value) for m in matches]
        if selector.kind is SelectorKind.REGEX:
            return regex_select(self.text(), selector.query)
        return [self.text()]

    def text(self) -> str:
        """Returns the JSON pretty-printed as one string."""
        return json.dumps(self._data, indent=2, ensure_ascii=False)

    def raw(self) -> bytes:
        """Returns the original response body, untouched."""
        return self._raw


def _value_to_plain(value: Any) -> str | Mapping[str, Any]:
    """Keeps strings and dicts as they are; renders other JSON values (numbers,
    booleans, null, lists) as their JSON text so nothing parser-specific leaks out."""
    if isinstance(value, str | Mapping):
        return value
    return json.dumps(value, ensure_ascii=False)

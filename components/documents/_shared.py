"""Small helpers shared by all Document implementations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from core.contracts.document import UnsupportedSelectorError
from core.models.selector import SelectorKind


def require_capability(
    capabilities: frozenset[SelectorKind], kind: SelectorKind, document_name: str
) -> None:
    """Raises UnsupportedSelectorError if this document type cannot run the given selector kind."""
    if kind not in capabilities:
        supported = sorted(k.value for k in capabilities)
        raise UnsupportedSelectorError(
            f"{document_name} does not support {kind.value!r} selectors; supported: {supported}"
        )


def regex_select(text: str, pattern: str) -> list[str | Mapping[str, Any]]:
    """Runs a regex over the text and returns group 1 (or the whole match) for every hit."""
    results: list[str | Mapping[str, Any]] = []
    for match in re.finditer(pattern, text):
        results.append(match.group(1) if match.groups() else match.group(0))
    return results

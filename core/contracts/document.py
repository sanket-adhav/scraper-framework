"""Document contract — the uniform query interface every parser output honors (plan2.md §5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from core.errors.exceptions import ScraperError
from core.models.selector import Selector, SelectorKind


class UnsupportedSelectorError(ScraperError):
    """select() was called with a SelectorKind outside this document's capabilities.

    In practice this never fires at runtime: load-time capability checking
    (core/config/capability_check.py, Plan 02/03) rejects mismatched specs first.
    """


@runtime_checkable
class Document(Protocol):
    content_type: str
    capabilities: frozenset[SelectorKind]

    def select(self, selector: Selector) -> list[str | Mapping[str, Any]]:
        """Run a query; results are plain strings/mappings only — never parser-native nodes."""
        ...

    def text(self) -> str:
        """Plain-text projection of the whole document."""
        ...

    def raw(self) -> bytes:
        """The original response body, always retained."""
        ...

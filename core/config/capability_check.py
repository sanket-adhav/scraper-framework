"""Load-time capability check (plan2.md §5).

Verifies that every selector kind an extraction spec uses is supported by the
Document type the configured parser produces — so a bad config fails at
startup with a clear message, never mid-scrape at 2 a.m.

This is a pure function on purpose: the config loader (Plan 03) wires it in.
"""

from __future__ import annotations

from collections.abc import Mapping

from core.errors.exceptions import ScraperError
from core.models.selector import SelectorKind


class CapabilityError(ScraperError):
    """An extraction spec asks for a selector kind its document type cannot run."""


def check_spec_against_capabilities(
    field_kinds: Mapping[str, SelectorKind],
    capabilities: frozenset[SelectorKind],
    document_type_name: str,
) -> None:
    """Raises CapabilityError naming every spec field whose selector kind the
    given document type does not support; does nothing if all fields are fine."""
    supported = sorted(kind.value for kind in capabilities)
    problems = [
        f"field {name!r} uses selector kind {kind.value!r}, but {document_type_name} "
        f"only supports {supported}"
        for name, kind in field_kinds.items()
        if kind not in capabilities
    ]
    if problems:
        raise CapabilityError(
            "extraction spec does not match document capabilities:\n  - " + "\n  - ".join(problems)
        )

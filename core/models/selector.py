"""Selector model — how extraction specs address content inside a Document (plan2.md §5)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SelectorKind(StrEnum):
    """Query languages a Document implementation may declare in its capabilities."""

    CSS = "css"  # HTML/XML documents
    XPATH = "xpath"  # HTML/XML documents
    JSONPATH = "jsonpath"  # JSON documents
    REGEX = "regex"  # any document with a text projection
    TEXT = "text"  # full plain-text view (PDF, fallback)


@dataclass(frozen=True, slots=True)
class Selector:
    kind: SelectorKind
    query: str

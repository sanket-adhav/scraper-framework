"""ScrapeRequest model and builder (plan2.md §3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class ScrapeRequest:
    url: str
    method: str = "GET"
    headers: Mapping[str, str] = field(default_factory=dict)
    cookies: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    priority: int = 0
    attempt: int = 0

    def with_attempt(self, attempt: int) -> ScrapeRequest:
        """A retry is a new immutable request with a bumped attempt counter."""
        return replace(self, attempt=attempt)


class ScrapeRequestBuilder:
    """Fluent construction of a ScrapeRequest without exposing mutable state."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._method = "GET"
        self._headers: dict[str, str] = {}
        self._cookies: dict[str, str] = {}
        self._metadata: dict[str, Any] = {}
        self._priority = 0

    def method(self, method: str) -> Self:
        self._method = method.upper()
        return self

    def header(self, name: str, value: str) -> Self:
        self._headers[name] = value
        return self

    def cookie(self, name: str, value: str) -> Self:
        self._cookies[name] = value
        return self

    def meta(self, key: str, value: Any) -> Self:
        self._metadata[key] = value
        return self

    def priority(self, priority: int) -> Self:
        self._priority = priority
        return self

    def build(self) -> ScrapeRequest:
        return ScrapeRequest(
            url=self._url,
            method=self._method,
            headers=dict(self._headers),
            cookies=dict(self._cookies),
            metadata=dict(self._metadata),
            priority=self._priority,
        )

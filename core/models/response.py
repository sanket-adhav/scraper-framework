"""Response model — what a Fetcher returns, regardless of transport (plan2.md §3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    elapsed_ms: float = 0.0
    content_type: str | None = None

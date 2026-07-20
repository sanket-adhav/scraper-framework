"""ScrapeJob — one unit of scraping work, serializable from day one (plan2.md §8).

Plan 09's distributed queue depends on jobs surviving a plain-dict round trip,
so that property is built and tested now, not retrofitted.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.models.scrape_request import ScrapeRequest


@dataclass(frozen=True, slots=True)
class ScrapeJob:
    """One scraping job: seed requests plus per-job config overrides."""

    requests: tuple[ScrapeRequest, ...]
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    plugin: str | None = None
    config_overrides: Mapping[str, Any] = field(default_factory=dict)
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Turns the job into a plain dict safe for JSON / a message queue."""
        return {
            "job_id": self.job_id,
            "plugin": self.plugin,
            "priority": self.priority,
            "config_overrides": dict(self.config_overrides),
            "requests": [_request_to_dict(r) for r in self.requests],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ScrapeJob:
        """Rebuilds a job from the plain dict produced by to_dict()."""
        return cls(
            job_id=data["job_id"],
            plugin=data.get("plugin"),
            priority=int(data.get("priority", 0)),
            config_overrides=dict(data.get("config_overrides", {})),
            requests=tuple(_request_from_dict(r) for r in data["requests"]),
        )


def _request_to_dict(request: ScrapeRequest) -> dict[str, Any]:
    """Turns one ScrapeRequest into a plain dict."""
    return {
        "url": request.url,
        "method": request.method,
        "headers": dict(request.headers),
        "cookies": dict(request.cookies),
        "metadata": dict(request.metadata),
        "priority": request.priority,
        "attempt": request.attempt,
    }


def _request_from_dict(data: Mapping[str, Any]) -> ScrapeRequest:
    """Rebuilds one ScrapeRequest from a plain dict."""
    return ScrapeRequest(
        url=data["url"],
        method=data.get("method", "GET"),
        headers=dict(data.get("headers", {})),
        cookies=dict(data.get("cookies", {})),
        metadata=dict(data.get("metadata", {})),
        priority=int(data.get("priority", 0)),
        attempt=int(data.get("attempt", 0)),
    )

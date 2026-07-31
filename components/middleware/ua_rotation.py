"""User-agent rotation middleware (plan2.md §6, §12, Plan 07).

Rotates through COHERENT profiles — a User-Agent paired with matching client
hint headers — never a random UA with mismatched headers, which is itself a
bot signal. Only sets headers the request hasn't already set.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from core.contracts.middleware import Next
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

# Each profile is a self-consistent header set. Real deployments load these from
# config; these defaults keep UA and its client hints agreeing.
DEFAULT_PROFILES: Sequence[Mapping[str, str]] = (
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA-Platform": '"Windows"',
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA-Platform": '"macOS"',
    },
)


class UaRotationMiddleware:
    """Middleware that cycles through coherent UA + header profiles per request."""

    def __init__(self, profiles: Sequence[Mapping[str, str]] | None = None) -> None:
        """Stores the header profiles to rotate (validated non-empty)."""
        self._profiles = [dict(p) for p in (profiles or DEFAULT_PROFILES)]
        if not self._profiles:
            raise ValueError("ua_rotation needs at least one profile")
        self._next = 0

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Applies the next profile's headers (without overriding the request's own)."""
        profile = self._profiles[self._next % len(self._profiles)]
        self._next += 1
        merged = {**profile, **dict(request.headers)}
        return await next(replace(request, headers=merged))

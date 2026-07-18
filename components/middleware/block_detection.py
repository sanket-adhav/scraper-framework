"""Block-detection middleware (plan2.md §12 — a Phase-1 concern, not a footnote).

Blocking often looks like success: a 200 response carrying a CAPTCHA page would
silently poison the data. This middleware classifies every response — real
content / soft block / CAPTCHA / hard block — using per-plugin signature config,
and raises FetchError(blocked=True) so a blocked page never reaches the parser.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum

from core.contracts.middleware import Next
from core.errors.exceptions import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


class BlockKind(StrEnum):
    """What kind of page came back, as far as blocking is concerned."""

    CONTENT = "content"
    SOFT_BLOCK = "soft_block"
    CAPTCHA = "captcha"
    HARD_BLOCK = "hard_block"


DEFAULT_SIGNATURES: Mapping[str, Sequence[str]] = {
    BlockKind.CAPTCHA: ("captcha", "are you a robot", "unusual traffic", "recaptcha"),
    BlockKind.SOFT_BLOCK: ("access denied", "temporarily blocked", "request blocked"),
}


class BlockDetectionMiddleware:
    """Middleware that rejects blocked/CAPTCHA responses before anything trusts them."""

    def __init__(
        self,
        signatures: Mapping[str, Sequence[str]] | None = None,
        hard_block_statuses: Sequence[int] = (403,),
    ) -> None:
        """Stores the text signatures (per-plugin config later) and hard-block statuses."""
        merged = dict(DEFAULT_SIGNATURES)
        for kind, sigs in (signatures or {}).items():
            merged[BlockKind(kind)] = tuple(sigs)
        self._signatures = {kind: tuple(s.lower() for s in sigs) for kind, sigs in merged.items()}
        self._hard_statuses = frozenset(hard_block_statuses)

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Fetches, classifies the response, and raises a typed error unless it's real content."""
        response = await next(request)
        kind = self.classify(response)
        if kind is not BlockKind.CONTENT:
            raise FetchError(
                f"{request.url} blocked ({kind.value}, status {response.status})",
                transient=False,
                blocked=True,
            )
        return response

    def classify(self, response: Response) -> BlockKind:
        """Decides whether a response is real content or one of the block kinds."""
        if response.status in self._hard_statuses:
            return BlockKind.HARD_BLOCK
        text = response.body.decode("utf-8", errors="ignore").lower()
        for kind in (BlockKind.CAPTCHA, BlockKind.SOFT_BLOCK):
            if any(sig in text for sig in self._signatures.get(kind, ())):
                return kind
        return BlockKind.CONTENT

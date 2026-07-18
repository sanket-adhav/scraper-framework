"""HTTP(S) fetcher backed by httpx — async, with fingerprint-relevant knobs (plan2.md §12)."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx

from core.errors.exceptions import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest

_TRANSIENT_ERRORS = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


class HttpFetcher:
    """Fetches requests over HTTP(S). Errors become typed FetchErrors; any status
    (including 4xx/5xx) comes back as a Response for middleware to judge."""

    def __init__(
        self,
        *,
        timeout_s: float = 30.0,
        follow_redirects: bool = True,
        verify_tls: bool = True,
        http2: bool = False,
        default_headers: Mapping[str, str] | None = None,
        transport: Any = None,
    ) -> None:
        """Builds the underlying httpx client; `transport` is injectable so tests
        can use httpx.MockTransport and stay fully offline."""
        self._client = httpx.AsyncClient(
            timeout=timeout_s,
            follow_redirects=follow_redirects,
            verify=verify_tls,
            http2=http2,
            headers=dict(default_headers or {}),
            transport=transport,
        )

    async def fetch(self, request: ScrapeRequest) -> Response:
        """Performs one HTTP request and returns the framework Response."""
        started = time.monotonic()
        try:
            reply = await self._client.request(
                request.method,
                request.url,
                headers=dict(request.headers),
                cookies=dict(request.cookies),
            )
        except _TRANSIENT_ERRORS as err:
            raise FetchError(f"{request.url}: {err!r}", transient=True) from err
        except httpx.HTTPError as err:
            raise FetchError(f"{request.url}: {err!r}", transient=False) from err
        elapsed_ms = (time.monotonic() - started) * 1000
        content_type = reply.headers.get("content-type")
        return Response(
            status=reply.status_code,
            headers=dict(reply.headers),
            body=reply.content,
            elapsed_ms=elapsed_ms,
            content_type=content_type.split(";")[0].strip() if content_type else None,
        )

    async def aclose(self) -> None:
        """Closes the underlying HTTP client and its connections."""
        await self._client.aclose()

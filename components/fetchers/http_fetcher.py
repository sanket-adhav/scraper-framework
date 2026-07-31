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
        self._client_kwargs: dict[str, Any] = {
            "timeout": timeout_s,
            "follow_redirects": follow_redirects,
            "verify": verify_tls,
            "http2": http2,
            "headers": dict(default_headers or {}),
            "transport": transport,
        }
        self._client = httpx.AsyncClient(**self._client_kwargs)
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}

    def _client_for(self, request: ScrapeRequest) -> httpx.AsyncClient:
        """Returns the client for this request — a per-proxy client if one was set
        by the proxy-rotation middleware, else the default shared client."""
        proxy = request.metadata.get("proxy")
        if not proxy:
            return self._client
        if proxy not in self._proxy_clients:
            self._proxy_clients[proxy] = httpx.AsyncClient(
                **{**self._client_kwargs, "proxy": str(proxy)}
            )
        return self._proxy_clients[proxy]

    async def fetch(self, request: ScrapeRequest) -> Response:
        """Performs one HTTP request and returns the framework Response."""
        started = time.monotonic()
        try:
            reply = await self._client_for(request).request(
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
        """Closes the default client and every per-proxy client."""
        await self._client.aclose()
        for client in self._proxy_clients.values():
            await client.aclose()

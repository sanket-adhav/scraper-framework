"""Token/OAuth2 login provider: exchanges credentials for a bearer token (Plan 07).

Uses an injectable async token endpoint so tests stay offline. The token becomes
a session header attached to every request by the auth middleware.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from core.contracts.login_provider import Session, SessionContext
from core.errors.exceptions import AuthError

TokenEndpoint = Callable[[SessionContext], Awaitable[Mapping[str, Any]]]


class TokenLoginProvider:
    """Gets a bearer token from an OAuth2-style endpoint and rides it as a header."""

    def __init__(
        self,
        token_url: str = "",
        *,
        header_name: str = "Authorization",
        header_prefix: str = "Bearer ",
        default_ttl_s: float = 3600.0,
        endpoint: TokenEndpoint | None = None,
        transport: Any = None,
    ) -> None:
        """Stores the token endpoint config; `endpoint`/`transport` are injectable for tests."""
        self._token_url = token_url
        self._header_name = header_name
        self._header_prefix = header_prefix
        self._default_ttl_s = default_ttl_s
        self._endpoint = endpoint or self._http_endpoint
        self._transport = transport

    async def acquire(self, ctx: SessionContext) -> Session:
        """Requests a token with the client credentials and returns it as a session header."""
        payload = await self._endpoint(ctx)
        token = payload.get("access_token")
        if not token:
            raise AuthError(f"token endpoint returned no access_token for {ctx.account}")
        ttl = float(payload.get("expires_in", self._default_ttl_s))
        return Session(
            headers={self._header_name: f"{self._header_prefix}{token}", "_ttl": str(ttl)}
        )

    async def is_valid(self, session: Session) -> bool:
        """True while the token is within its lifetime (minus a safety margin)."""
        ttl = float(session.headers.get("_ttl", self._default_ttl_s))
        age = time.time() - session.acquired_at.timestamp()
        return age < (ttl - 30)

    async def _http_endpoint(self, ctx: SessionContext) -> Mapping[str, Any]:
        """Default endpoint: POST client-credentials to the token URL."""
        async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
            reply = await client.post(
                self._token_url or ctx.login_url,
                data={"grant_type": "client_credentials", **dict(ctx.credentials)},
            )
            if reply.status_code != 200:
                raise AuthError(f"token endpoint returned {reply.status_code} for {ctx.account}")
            return dict(reply.json())

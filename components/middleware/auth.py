"""Auth/session middleware (plan2.md §6, Plan 07).

Attaches the stored session (cookies + headers) to each request. If the session
is stale (per is_valid, or a 401 / login-redirect signal), it re-acquires via
the LoginProvider EXACTLY ONCE, then fails permanent — no infinite login loops.
"""

from __future__ import annotations

from dataclasses import replace

from core.contracts.login_provider import LoginProvider, Session, SessionContext
from core.contracts.middleware import Next
from core.errors.exceptions import AuthError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


class SessionStore:
    """The tiny surface auth needs from a session store (get/put by plugin+account)."""

    def get(self, plugin: str, account: str) -> Session | None: ...  # pragma: no cover
    def put(self, plugin: str, account: str, session: Session) -> None: ...  # pragma: no cover


class AuthMiddleware:
    """Middleware that keeps requests authenticated, refreshing the session once when stale."""

    def __init__(
        self,
        provider: LoginProvider,
        session_ctx: SessionContext,
        store: SessionStore | None = None,
        login_redirect_statuses: tuple[int, ...] = (401,),
    ) -> None:
        """Remembers the login provider, the session context, and an optional store."""
        self._provider = provider
        self._ctx = session_ctx
        self._store = store
        self._statuses = login_redirect_statuses
        self._session: Session | None = None

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Attaches the session, and on an auth failure re-logs in once before giving up."""
        session = await self._current_session()
        response = await next(_apply(request, session))
        if response.status in self._statuses:
            session = await self._reacquire()  # exactly one refresh attempt
            response = await next(_apply(request, session))
            if response.status in self._statuses:
                raise AuthError(
                    f"still unauthorized after one re-login for {self._ctx.account} "
                    f"(status {response.status})"
                )
        return response

    async def _current_session(self) -> Session:
        """Returns a valid session, loading from the store or logging in as needed."""
        if self._session is None and self._store is not None:
            self._session = self._store.get(self._ctx.plugin, self._ctx.account)
        if self._session is not None and await self._provider.is_valid(self._session):
            return self._session
        return await self._reacquire()

    async def _reacquire(self) -> Session:
        """Logs in fresh via the provider and persists the new session."""
        self._session = await self._provider.acquire(self._ctx)
        if self._store is not None:
            self._store.put(self._ctx.plugin, self._ctx.account, self._session)
        return self._session


def _apply(request: ScrapeRequest, session: Session) -> ScrapeRequest:
    """Returns a copy of the request with the session's cookies and headers attached.
    Internal session keys (leading underscore, e.g. _ttl) are never sent."""
    session_headers = {k: v for k, v in session.headers.items() if not k.startswith("_")}
    return replace(
        request,
        headers={**session_headers, **dict(request.headers)},
        cookies={**dict(session.cookies), **dict(request.cookies)},
    )

"""LoginProvider contract — acquires and checks authenticated sessions (plan2.md §3).

Session and SessionContext are deliberately minimal stubs: concrete session
shape (cookies, tokens, persistence, encryption) is Plan 07 territory, and
guessing it now would be designing in a vacuum.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.errors.exceptions import ScraperError


class AuthError(ScraperError):
    """Login failed or a session could not be refreshed."""


@runtime_checkable
class Session(Protocol):
    """Opaque authenticated state a fetch can be performed with."""


@runtime_checkable
class SessionContext(Protocol):
    """What a LoginProvider needs to acquire a session (credentials refs, target info)."""


@runtime_checkable
class LoginProvider(Protocol):
    async def acquire(self, ctx: SessionContext) -> Session: ...

    async def is_valid(self, session: Session) -> bool: ...

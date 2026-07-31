"""LoginProvider contract and the concrete Session model (plan2.md §3, Plan 07).

A Session is the authenticated state (cookies + headers) a fetch rides on.
A LoginProvider knows how to acquire one and check whether it's still valid.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from core.errors.exceptions import AuthError

__all__ = ["AuthError", "LoginProvider", "Session", "SessionContext"]


@dataclass(frozen=True, slots=True)
class Session:
    """Authenticated state: cookies and headers to attach, plus when it was acquired."""

    cookies: Mapping[str, str] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    acquired_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class SessionContext:
    """What a LoginProvider needs to log in: the target and resolved credentials."""

    plugin: str
    account: str
    login_url: str = ""
    credentials: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class LoginProvider(Protocol):
    async def acquire(self, ctx: SessionContext) -> Session:
        """Logs in and returns a fresh Session."""
        ...

    async def is_valid(self, session: Session) -> bool:
        """Reports whether the session is still usable (not expired/logged out)."""
        ...

"""Form login provider: drives a Playwright login flow and captures the cookies (Plan 07).

The browser flow is injectable (a callable returning cookies), so tests run
without a real browser; production uses a Playwright page to fill and submit
the login form.
"""
# handles login
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from core.contracts.login_provider import Session, SessionContext
from core.errors.exceptions import AuthError

LoginFlow = Callable[[SessionContext], Awaitable[Mapping[str, str]]]


class FormLoginProvider:
    """Logs in through an HTML form and keeps the resulting session cookies."""

    def __init__(
        self,
        *,
        username_selector: str = "input[name=username]",
        password_selector: str = "input[name=password]",
        submit_selector: str = "button[type=submit]",
        success_check: str = "",
        browser_factory: Callable[[], Awaitable[Any]] | None = None,
        login_flow: LoginFlow | None = None,
    ) -> None:
        """Stores the form selectors; `login_flow`/`browser_factory` are injectable for tests."""
        self._username_selector = username_selector
        self._password_selector = password_selector
        self._submit_selector = submit_selector
        self._success_check = success_check
        self._browser_factory = browser_factory
        self._login_flow = login_flow or self._playwright_flow

    async def acquire(self, ctx: SessionContext) -> Session:
        """Runs the login flow and returns a session carrying the captured cookies."""
        cookies = await self._login_flow(ctx)
        if not cookies:
            raise AuthError(f"form login for {ctx.account} produced no cookies")
        return Session(cookies=dict(cookies))

    async def is_valid(self, session: Session) -> bool:
        """A form session is valid as long as it still has cookies (401s trigger re-login)."""
        return bool(session.cookies)

    async def _playwright_flow(self, ctx: SessionContext) -> Mapping[str, str]:
        """Default flow: open the login page, fill the form, submit, harvest cookies."""
        if self._browser_factory is None:
            raise AuthError("form login needs a browser_factory (or an injected login_flow)")
        browser = await self._browser_factory()
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(ctx.login_url)
            await page.fill(self._username_selector, ctx.credentials.get("username", ""))
            await page.fill(self._password_selector, ctx.credentials.get("password", ""))
            await page.click(self._submit_selector)
            if self._success_check:
                await page.wait_for_selector(self._success_check)
            cookies = {c["name"]: c["value"] for c in await context.cookies()}
            await context.close()
            return cookies
        finally:
            await browser.close()

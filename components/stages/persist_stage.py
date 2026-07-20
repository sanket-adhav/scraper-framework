"""The persist pipeline stage: saves ctx.record to every configured repository."""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Any

from core.contracts.repository import Repository
from core.contracts.stage import Context, ErrorAction
from core.errors.exceptions import PersistError, ScraperError


class PersistStage:
    """Pipeline stage that writes the finished record to the configured repositories."""

    name = "persist"

    def __init__(self, repositories: Sequence[Repository]) -> None:
        """Remembers where records get saved (usually one repository)."""
        self._repositories = list(repositories)

    async def run(self, ctx: Context) -> Context:
        """Saves the record everywhere it belongs.  Repositories whose save()
        accepts a ``raw_body`` keyword argument receive the response bytes
        along with headers and cookies from the fetch context."""
        if ctx.record is None:
            raise PersistError("persist stage needs ctx.record, but none was set")
        raw_body = ctx.response.body if ctx.response else None

        # Extract headers and cookies from the request
        headers = dict(ctx.request.headers) if ctx.request else {}
        cookies = dict(ctx.request.cookies) if ctx.request else {}

        # Also extract cookies from response's Set-Cookie headers if present
        if ctx.response:
            import re
            for k, v in ctx.response.headers.items():
                if k.lower() == "set-cookie":
                    for cookie in re.split(r",(?=[^ ;]+=)", v):
                        pair = cookie.split(";", 1)[0].strip()
                        if "=" in pair:
                            name, val = pair.split("=", 1)
                            cookies[name.strip()] = val.strip()

        for repository in self._repositories:
            sig = inspect.signature(repository.save)
            if "raw_body" in sig.parameters:
                # Build kwargs dynamically based on what the repository accepts
                kwargs: dict[str, Any] = {"raw_body": raw_body}
                if "headers" in sig.parameters:
                    kwargs["headers"] = headers
                if "cookies" in sig.parameters:
                    kwargs["cookies"] = cookies
                await repository.save(ctx.record, **kwargs)
            else:
                await repository.save(ctx.record)
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Fallback when config is silent: retry transient storage trouble, abort the rest."""
        if isinstance(err, PersistError) and err.transient:
            return ErrorAction.RETRY
        return ErrorAction.ABORT

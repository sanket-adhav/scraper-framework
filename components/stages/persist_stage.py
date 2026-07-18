"""The persist pipeline stage: saves ctx.record to every configured repository."""

from __future__ import annotations

from collections.abc import Sequence

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
        """Saves the record everywhere it belongs."""
        if ctx.record is None:
            raise PersistError("persist stage needs ctx.record, but none was set")
        for repository in self._repositories:
            await repository.save(ctx.record)
        return ctx

    def on_error(self, ctx: Context, err: ScraperError) -> ErrorAction:
        """Fallback when config is silent: retry transient storage trouble, abort the rest."""
        if isinstance(err, PersistError) and err.transient:
            return ErrorAction.RETRY
        return ErrorAction.ABORT

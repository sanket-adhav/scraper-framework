"""The pipeline runner: executes the ordered stage list over a Context (plan2.md §4).

Deliberately boring. It runs stages in order, applies the error policy
(RETRY / SKIP / QUARANTINE / ABORT), enforces per-stage timeouts, and emits
events. It does not know or care what any stage does.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from core.contracts.stage import ErrorAction, Stage
from core.errors.exceptions import ScraperError, StageTimeoutError
from core.errors.policy import ErrorPolicy
from core.errors.quarantine import QuarantineRecord, QuarantineSink
from core.events.bus import EventBus
from core.events.types import (
    RECORD_QUARANTINED,
    STAGE_COMPLETED,
    STAGE_FAILED,
    STAGE_RETRYING,
    STAGE_STARTED,
    Event,
)
from core.pipeline.context import Context


class PipelineStatus(StrEnum):
    """How one trip through the pipeline ended."""

    COMPLETED = "completed"
    ABORTED = "aborted"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """The outcome of one pipeline run: final status, final context, and any failure info."""

    status: PipelineStatus
    context: Context
    failed_stage: str | None = None
    error: ScraperError | None = None


class PipelineRunner:
    """Runs a fixed, ordered list of stages and applies the configured error policy."""

    def __init__(
        self,
        stages: Sequence[Stage],
        policy: ErrorPolicy,
        *,
        timeouts: Mapping[str, float] | None = None,
        bus: EventBus | None = None,
        quarantine: QuarantineSink | None = None,
    ) -> None:
        """Stores the stage list, error policy, per-stage timeouts, event bus, and sink."""
        self._stages = list(stages)
        self._policy = policy
        self._timeouts = dict(timeouts or {})
        self._bus = bus or EventBus()
        self._quarantine = quarantine

    async def run(self, ctx: Context) -> PipelineResult:
        """Runs every stage in order on the context and returns how it ended."""
        for stage in self._stages:
            outcome = await self._run_stage(stage, ctx)
            if outcome is not None:
                return outcome
        return PipelineResult(status=PipelineStatus.COMPLETED, context=ctx)

    async def _run_stage(self, stage: Stage, ctx: Context) -> PipelineResult | None:
        """Runs one stage with retries per policy; returns a result only to stop the pipeline."""
        attempts = 0
        while True:
            self._emit(STAGE_STARTED, ctx, stage)
            try:
                await self._run_once(stage, ctx)
            except Exception as raw:  # noqa: BLE001 — every failure goes through the policy
                error = _as_scraper_error(raw, stage.name)
                action = self._action_for(stage, ctx, error)
                if action is ErrorAction.RETRY:
                    if attempts < self._policy.max_retries:
                        attempts += 1
                        self._emit(STAGE_RETRYING, ctx, stage, attempt=attempts)
                        continue
                    action = self._policy.on_retry_exhausted
                    if action is ErrorAction.RETRY:  # config must not loop forever
                        action = ErrorAction.ABORT
                if action is ErrorAction.SKIP:
                    self._emit(STAGE_FAILED, ctx, stage, action="skip", error=str(error))
                    return None
                if action is ErrorAction.QUARANTINE:
                    self._put_quarantine(stage, ctx, error)
                    self._emit(RECORD_QUARANTINED, ctx, stage, error=str(error))
                    return PipelineResult(
                        PipelineStatus.QUARANTINED, ctx, failed_stage=stage.name, error=error
                    )
                self._emit(STAGE_FAILED, ctx, stage, action="abort", error=str(error))
                return PipelineResult(
                    PipelineStatus.ABORTED, ctx, failed_stage=stage.name, error=error
                )
            else:
                self._emit(STAGE_COMPLETED, ctx, stage)
                return None

    async def _run_once(self, stage: Stage, ctx: Context) -> None:
        """Runs a stage a single time, enforcing its timeout if one is configured."""
        timeout = self._timeouts.get(stage.name)
        if timeout is None:
            await stage.run(ctx)
        else:
            try:
                await asyncio.wait_for(stage.run(ctx), timeout=timeout)
            except TimeoutError as err:
                raise StageTimeoutError(
                    f"stage {stage.name!r} exceeded its {timeout}s time limit"
                ) from err

    def _action_for(self, stage: Stage, ctx: Context, error: ScraperError) -> ErrorAction:
        """Picks the error action: config policy first, then the stage's own fallback."""
        configured = self._policy.action_for(stage.name, error)
        if configured is not None:
            return configured
        try:
            return stage.on_error(ctx, error)
        except Exception:  # noqa: BLE001 — a broken on_error must not mask the real failure
            return self._policy.default

    def _put_quarantine(self, stage: Stage, ctx: Context, error: ScraperError) -> None:
        """Writes a needs-review snapshot of the failed context, if a sink is configured."""
        if self._quarantine is None:
            return
        self._quarantine.put(
            QuarantineRecord(
                trace_id=ctx.trace_id,
                stage=stage.name,
                error_type=type(error).__name__,
                error_message=str(error),
                context_snapshot={
                    "url": ctx.request.url if ctx.request else None,
                    "has_response": ctx.response is not None,
                    "record": dict(ctx.record.data) if ctx.record else None,
                    "config_fingerprint": ctx.config_fingerprint,
                },
            )
        )

    def _emit(self, event_type: str, ctx: Context, stage: Stage, **extra: object) -> None:
        """Publishes one pipeline event with the trace id and stage name attached."""
        payload: dict[str, object] = {"trace_id": ctx.trace_id, "stage": stage.name, **extra}
        self._bus.publish(Event(type=event_type, payload=payload))


def _as_scraper_error(raw: Exception, stage_name: str) -> ScraperError:
    """Passes ScraperErrors through and wraps anything unexpected so policy can apply."""
    if isinstance(raw, ScraperError):
        return raw
    wrapped = ScraperError(f"unexpected error in stage {stage_name!r}: {raw!r}")
    wrapped.__cause__ = raw
    return wrapped

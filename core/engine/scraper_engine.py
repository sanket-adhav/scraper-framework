"""The Scraper Engine: takes a job, runs each request through the pipeline,
and feeds discovered requests (pagination, crawling) back into the work queue.

Same engine for both modes (plan2.md §16): with no `discovered_sink` it drains
discovered requests in an in-process deque (single-process mode); with a sink
(a queue's submit) it hands discovered requests off as new jobs, so N workers
share the crawl — a config flag, not a code change.
"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from core.config.loader import ResolvedConfig
from core.events.bus import EventBus
from core.events.types import JOB_COMPLETED, JOB_STARTED, Event
from core.models.job import ScrapeJob
from core.models.scrape_request import ScrapeRequest
from core.pipeline.context import Context
from core.pipeline.runner import PipelineResult, PipelineRunner, PipelineStatus

DiscoveredSink = Callable[[ScrapeRequest], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class JobResult:
    """Summary of one finished job: how many requests ended in each status."""

    job_id: str
    completed: int = 0
    aborted: int = 0
    quarantined: int = 0
    results: tuple[PipelineResult, ...] = field(default_factory=tuple)


class ScraperEngine:
    """Coordinates one job: pipeline per request, discovered requests fed back in."""

    def __init__(
        self,
        runner: PipelineRunner,
        config: ResolvedConfig,
        *,
        bus: EventBus | None = None,
        discovered_sink: DiscoveredSink | None = None,
    ) -> None:
        """Stores the pipeline runner, config, bus, and an optional sink for
        discovered requests (a queue's submit) that enables distributed mode."""
        self._runner = runner
        self._config = config
        self._bus = bus or EventBus()
        self._discovered_sink = discovered_sink
        engine_cfg = config.data.get("engine") or {}
        self._max_requests = int(engine_cfg.get("max_requests", 1000))

    async def run(self, job: ScrapeJob) -> JobResult:
        """Runs every request in the job and returns the summary. Discovered
        requests either drain in-process (no sink) or go to the queue (sink set)."""
        self._bus.publish(Event(JOB_STARTED, {"job_id": job.job_id}))
        pending: deque[ScrapeRequest] = deque(job.requests)
        results: list[PipelineResult] = []
        counts = dict.fromkeys(PipelineStatus, 0)

        while pending and len(results) < self._max_requests:
            request = pending.popleft()
            ctx = Context(
                trace_id=uuid.uuid4().hex,
                config=self._config.data,
                config_fingerprint=self._config.fingerprint,
                request=request,
            )
            result = await self._runner.run(ctx)
            results.append(result)
            counts[result.status] += 1
            if self._discovered_sink is None:
                pending.extend(result.context.discovered_requests)
            else:
                for discovered in result.context.discovered_requests:
                    await self._discovered_sink(discovered)

        summary = JobResult(
            job_id=job.job_id,
            completed=counts[PipelineStatus.COMPLETED],
            aborted=counts[PipelineStatus.ABORTED],
            quarantined=counts[PipelineStatus.QUARANTINED],
            results=tuple(results),
        )
        self._bus.publish(
            Event(
                JOB_COMPLETED,
                {
                    "job_id": job.job_id,
                    "completed": summary.completed,
                    "aborted": summary.aborted,
                    "quarantined": summary.quarantined,
                },
            )
        )
        return summary

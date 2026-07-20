"""Distributed-tracing helpers (plan2.md §10).

OpenTelemetry spans per stage, wired from day one. The default OTel API is a
no-op until an SDK exporter is configured, so this costs almost nothing now and
becomes real cross-worker tracing in Plan 09 by flipping on an exporter — not a
retrofit.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace

_tracer = trace.get_tracer("scraper.pipeline")


@contextmanager
def stage_span(stage_name: str, trace_id: str) -> Iterator[None]:
    """Opens a span around one stage's execution, tagged with the trace id."""
    with _tracer.start_as_current_span(f"stage.{stage_name}") as span:
        span.set_attribute("scraper.stage", stage_name)
        span.set_attribute("scraper.trace_id", trace_id)
        yield

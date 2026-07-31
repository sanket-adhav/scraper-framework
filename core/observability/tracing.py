"""Distributed-tracing helpers (plan2.md §10).

OpenTelemetry spans per stage, wired from day one. The default OTel API is a
no-op until an SDK exporter is configured, so this costs almost nothing now and
becomes real cross-worker tracing in Plan 09 by flipping on an exporter — not a
retrofit.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace

_tracer = trace.get_tracer("scraper.pipeline")
_exporter_on = False


def enable_otlp_exporter(endpoint: str | None = None) -> bool:
    """Turns on real OTLP span export (Plan 09). Idempotent; returns whether it
    is now active. Without this the tracer is a no-op — the instrumentation cost
    was paid in Plan 08 so switching it on is a flag, not a retrofit."""
    global _exporter_on
    if _exporter_on:
        return True
    endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return False
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
                OTLPSpanExporter,
            )
        except ImportError:
            return False  # OTLP exporter package not installed — stay no-op
        provider = TracerProvider(resource=Resource.create({"service.name": "scraper"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        _exporter_on = True
        return True
    except Exception:  # noqa: BLE001 — tracing must never break a scrape
        return False


@contextmanager
def stage_span(stage_name: str, trace_id: str) -> Iterator[None]:
    """Opens a span around one stage's execution, tagged with the trace id."""
    with _tracer.start_as_current_span(f"stage.{stage_name}") as span:
        span.set_attribute("scraper.stage", stage_name)
        span.set_attribute("scraper.trace_id", trace_id)
        yield

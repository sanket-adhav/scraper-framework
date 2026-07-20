"""Prometheus metrics event listener (plan2.md §10).

Turns pipeline events into Prometheus counters/gauges: fetch/save throughput,
extraction success, per-field validation-failure rate, and block rate — the
series the block-rate and validation dashboards read.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter

from core.events.types import (
    BLOCK_DETECTED,
    RECORD_EXTRACTED,
    RECORD_SAVED,
    STAGE_COMPLETED,
    VALIDATION_FAILED,
    Event,
)


class MetricsListener:
    """Records pipeline events as Prometheus metrics on its own registry."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Builds the counter set on the given (or a fresh) Prometheus registry."""
        reg = registry or CollectorRegistry()
        self.registry = reg
        self.records_extracted = Counter(
            "scraper_records_extracted_total", "Records extracted", ["plugin"], registry=reg
        )
        self.records_saved = Counter(
            "scraper_records_saved_total", "Records saved", ["plugin"], registry=reg
        )
        self.blocks = Counter(
            "scraper_blocks_total", "Responses classified as blocked", ["plugin"], registry=reg
        )
        self.fetches = Counter(
            "scraper_fetches_total", "Fetch stage completions", ["plugin"], registry=reg
        )
        self.validation_failures = Counter(
            "scraper_validation_failures_total",
            "Per-field validation failures",
            ["plugin", "field"],
            registry=reg,
        )

    def __call__(self, event: Event) -> None:
        """Updates the relevant counter for one event."""
        plugin = str(event.payload.get("plugin", "-"))
        if event.type == RECORD_EXTRACTED:
            self.records_extracted.labels(plugin).inc()
        elif event.type == RECORD_SAVED:
            self.records_saved.labels(plugin).inc()
        elif event.type == BLOCK_DETECTED:
            self.blocks.labels(plugin).inc()
        elif event.type == STAGE_COMPLETED and event.payload.get("stage") == "fetch":
            self.fetches.labels(plugin).inc()
        elif event.type == VALIDATION_FAILED:
            for field in event.payload.get("fields", []):
                self.validation_failures.labels(plugin, str(field)).inc()

    def value(self, counter: Counter, **labels: str) -> float:
        """Reads a counter's current value (for tests/inspection)."""
        return float(counter.labels(*labels.values())._value.get())

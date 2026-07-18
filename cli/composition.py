"""The composition root: the one place that knows both core and components.

Registers every built-in component into a Registry and wires config-driven
pieces (like the fetch stage) together. The CLI (Plan 05) builds on this;
core never imports components, so this file is where the two sides meet.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from components.fetchers.http_fetcher import HttpFetcher
from components.fetchers.local_file_fetcher import LocalFileFetcher
from components.middleware.block_detection import BlockDetectionMiddleware
from components.middleware.observability import ObservabilityMiddleware
from components.middleware.rate_limiter import RateLimiterMiddleware
from components.middleware.retry import RetryMiddleware
from components.parsers.html_parser import HtmlParser
from components.parsers.json_parser import JsonParser
from components.parsers.pdf_parser import PdfParser
from components.parsers.text_parser import TextParser
from components.parsers.xml_parser import XmlParser
from components.stages.fetch_stage import FetchStage
from core.registry.factories import build_component
from core.registry.registry import Registry


def default_registry() -> Registry:
    """Returns a Registry with every built-in component registered by name."""
    registry = Registry()
    registry.register("fetcher", "http", HttpFetcher)
    registry.register("fetcher", "local_file", LocalFileFetcher)
    registry.register("parser", "html", HtmlParser)
    registry.register("parser", "json", JsonParser)
    registry.register("parser", "xml", XmlParser)
    registry.register("parser", "pdf", PdfParser)
    registry.register("parser", "text", TextParser)
    registry.register("middleware", "rate_limit", RateLimiterMiddleware)
    registry.register("middleware", "retry", RetryMiddleware)
    registry.register("middleware", "block_detection", BlockDetectionMiddleware)
    registry.register("middleware", "observability", ObservabilityMiddleware)
    return registry


def build_fetch_stage(registry: Registry, config: Mapping[str, Any]) -> FetchStage:
    """Builds the fetch stage from config: the named fetcher wrapped in the
    named middleware stack, in the configured order."""
    fetcher = build_component(
        registry, "fetcher", config.get("fetcher", "http"), config.get("fetcher_options")
    )
    middleware_options: Mapping[str, Any] = config.get("middleware_options") or {}
    middlewares = [
        build_component(registry, "middleware", name, middleware_options.get(name))
        for name in config.get("middleware", [])
    ]
    return FetchStage(fetcher, middlewares)


def register_fetch_stage(registry: Registry, config: Mapping[str, Any]) -> None:
    """Registers the config-wired fetch stage under the standard 'fetch' name."""
    registry.register("stage", "fetch", lambda: build_fetch_stage(registry, config))

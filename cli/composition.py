"""The composition root: the one place that knows both core and components.
connects to the stage names fields.
Registers every built-in component into a Registry and wires the config-driven
stages together. The CLI builds on this; core never imports components, so
this file is where the two sides meet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from components.extractors.spec_driven import SpecDrivenExtractor
from components.extractors.table_extractor import TableExtractor
from components.fetchers.authenticated_playwright_fetcher import AuthenticatedPlaywrightFetcher
from components.fetchers.http_fetcher import HttpFetcher
from components.fetchers.local_file_fetcher import LocalFileFetcher
from components.fetchers.playwright_fetcher import PlaywrightFetcher
from components.listeners.console_listener import ConsoleFeedbackListener
from components.listeners.logging_listener import LoggingListener
from components.listeners.metrics_listener import MetricsListener
from components.middleware.block_detection import BlockDetectionMiddleware
from components.middleware.caching import CachingMiddleware
from components.middleware.circuit_breaker import CircuitBreakerMiddleware
from components.middleware.cookie_manager import CookieManagerMiddleware
from components.middleware.cost_tracker import CostTrackerMiddleware
from components.middleware.observability import ObservabilityMiddleware
from components.middleware.proxy_rotation import ProxyRotationMiddleware
from components.middleware.rate_limiter import RateLimiterMiddleware
from components.middleware.retry import RetryMiddleware
from components.middleware.ua_rotation import UaRotationMiddleware
from components.parsers.auto_parser import AutoParser
from components.parsers.html_parser import HtmlParser
from components.parsers.json_parser import JsonParser
from components.parsers.pdf_parser import PdfParser
from components.parsers.text_parser import TextParser
from components.parsers.xml_parser import XmlParser
from components.repositories.csv_repository import CsvRepository
from components.repositories.file_repository import FileRepository
from components.repositories.json_repository import JsonRepository
from components.repositories.jsonl_repository import JsonlRepository
from components.repositories.postgres_repository import PostgresRepository
from components.stages.discover_stage import DiscoverStage
from components.stages.extract_stage import ExtractStage
from components.stages.fetch_stage import FetchStage
from components.stages.parse_stage import ParseStage
from components.stages.persist_stage import PersistStage
from components.stages.transform_stage import TransformStage
from components.stages.validate_stage import ValidateStage
from components.transformers.currency_normalizer import CurrencyNormalizer
from components.transformers.date_normalizer import DateNormalizer
from components.transformers.enum_mapper import EnumMapper
from components.transformers.field_enricher import FieldEnricher
from components.transformers.text_cleaner import TextCleaner
from components.transformers.unit_converter import UnitConverter
from components.validators.business_rule import BusinessRuleValidator
from components.validators.duplicate_detector import DuplicateDetectorValidator
from components.validators.required_field import RequiredFieldValidator
from components.validators.schema_validator import SchemaValidator
from components.validators.type_validator import TypeValidator
from core.config.schema import ExtractConfigModel
from core.contracts.parser import Parser
from core.errors.exceptions import ConfigError
from core.events.bus import EventBus
from core.registry.factories import build_component
from core.registry.registry import Registry


def default_registry() -> Registry:
    """Returns a Registry with every built-in component registered by name."""
    registry = Registry()
    registry.register("fetcher", "http", HttpFetcher)
    registry.register("fetcher", "local_file", LocalFileFetcher)
    registry.register("fetcher", "playwright", PlaywrightFetcher)
    registry.register("fetcher", "authenticated_playwright", AuthenticatedPlaywrightFetcher)
    registry.register("parser", "html", HtmlParser)
    registry.register("parser", "json", JsonParser)
    registry.register("parser", "xml", XmlParser)
    registry.register("parser", "pdf", PdfParser)
    registry.register("parser", "text", TextParser)
    registry.register("parser", "auto", AutoParser)
    registry.register("middleware", "rate_limit", RateLimiterMiddleware)
    registry.register("middleware", "retry", RetryMiddleware)
    registry.register("middleware", "block_detection", BlockDetectionMiddleware)
    registry.register("middleware", "observability", ObservabilityMiddleware)
    registry.register("middleware", "circuit_breaker", CircuitBreakerMiddleware)
    registry.register("middleware", "cache", CachingMiddleware)
    registry.register("middleware", "proxy_rotation", ProxyRotationMiddleware)
    registry.register("middleware", "ua_rotation", UaRotationMiddleware)
    registry.register("middleware", "cookie_manager", CookieManagerMiddleware)
    registry.register("middleware", "cost_tracker", CostTrackerMiddleware)
    registry.register("middleware", "distributed_rate_limit", _build_distributed_rate_limit)
    registry.register("extractor", "spec_driven", SpecDrivenExtractor)
    registry.register("extractor", "table", TableExtractor)
    registry.register("validator", "required_field", RequiredFieldValidator)
    registry.register("validator", "type", TypeValidator)
    registry.register("validator", "schema", SchemaValidator)
    registry.register("validator", "business_rule", BusinessRuleValidator)
    registry.register("validator", "duplicate", DuplicateDetectorValidator)
    registry.register("transformer", "currency", CurrencyNormalizer)
    registry.register("transformer", "date", DateNormalizer)
    registry.register("transformer", "text_cleaner", TextCleaner)
    registry.register("transformer", "unit_converter", UnitConverter)
    registry.register("transformer", "enum_mapper", EnumMapper)
    registry.register("transformer", "field_enricher", FieldEnricher)
    registry.register("repository", "csv", CsvRepository)
    registry.register("repository", "file", FileRepository)
    registry.register("repository", "json", JsonRepository)
    registry.register("repository", "jsonl", JsonlRepository)
    registry.register("repository", "postgres", PostgresRepository)
    return registry


def _build_distributed_rate_limit(
    dsn: str = "", rate: float = 1.0, burst: float = 1.0
) -> Any:
    """Builds the Postgres-shared rate limiter; DSN falls back to DATABASE_URL."""
    import os

    from components.middleware.distributed_rate_limiter import (
        DistributedRateLimiterMiddleware,
        PostgresTokenBucketStore,
    )

    resolved = dsn or os.environ.get("DATABASE_URL", "")
    if not resolved:
        raise ConfigError("distributed_rate_limit needs a Postgres dsn or DATABASE_URL")
    store = PostgresTokenBucketStore(resolved)
    return DistributedRateLimiterMiddleware(store, rate=rate, burst=burst)


def build_event_bus(metrics: MetricsListener | None = None) -> tuple[EventBus, MetricsListener]:
    """Builds an event bus with the default listeners attached: structured logging
    and Prometheus metrics both run purely as subscribers (plan2.md §10)."""
    bus = EventBus()
    metrics = metrics or MetricsListener()
    bus.subscribe("*", LoggingListener())
    bus.subscribe("*", ConsoleFeedbackListener())
    bus.subscribe("*", metrics)
    return bus, metrics


def build_fetch_stage(registry: Registry, config: Mapping[str, Any]) -> FetchStage:
    """Builds the fetch stage: the named fetcher wrapped in the named middleware stack."""
    fetcher = build_component(
        registry, "fetcher", config.get("fetcher", "http"), config.get("fetcher_options")
    )
    middleware_options: Mapping[str, Any] = config.get("middleware_options") or {}
    middlewares = [
        build_component(registry, "middleware", name, middleware_options.get(name))
        for name in config.get("middleware", [])
    ]
    return FetchStage(fetcher, middlewares)


def build_parse_stage(registry: Registry, config: Mapping[str, Any]) -> ParseStage:
    """Builds the parse stage from the config's declared parser.
    Defaults to 'auto' which dynamically routes by content-type."""
    parser_name = config.get("parser", "auto")
    parser: Parser
    if parser_name == "auto":
        # Build AutoParser with all known specialised parsers injected. It
        # satisfies the runtime Parser protocol; the cast is only needed because
        # its content_types/document_type are ClassVars (mypy strictness).
        specialised = [HtmlParser(), PdfParser(), JsonParser(), XmlParser(), TextParser()]
        parser = cast(Parser, AutoParser(parsers=specialised))
    else:
        parser = build_component(registry, "parser", parser_name, config.get("parser_options"))
    return ParseStage(parser)


def build_extract_stage(registry: Registry, config: Mapping[str, Any]) -> ExtractStage:
    """Builds the extract stage: the configured extractor plus the validated spec."""
    raw_spec = config.get("extract")
    if not raw_spec:
        raise ConfigError("pipeline has an extract stage but config has no `extract` section")
    spec = ExtractConfigModel.model_validate(raw_spec)
    plugin: Mapping[str, Any] = config.get("plugin") or {}
    extractor = build_component(
        registry,
        "extractor",
        config.get("extractor") or "spec_driven",
        {
            "plugin_name": str(plugin.get("name", "")),
            "plugin_version": str(plugin.get("version", "")),
            # Extractors that need more than the spec (e.g. `table`) read their
            # settings from here; `spec_driven` takes no options and ignores it.
            **(config.get("extractor_options") or {}),
        },
    )
    return ExtractStage(extractor, spec)


def _build_refs(registry: Registry, kind: str, refs: Sequence[Mapping[str, Any]]) -> list[Any]:
    """Builds a list of components from config refs: [{name, options}, ...]."""
    return [
        build_component(registry, kind, ref["name"], ref.get("options")) for ref in refs
    ]


def build_validate_stage(registry: Registry, config: Mapping[str, Any]) -> ValidateStage:
    """Builds the validate stage from the config's validator list."""
    section: Mapping[str, Any] = config.get("validate") or {}
    return ValidateStage(_build_refs(registry, "validator", section.get("validators", [])))


def build_transform_stage(registry: Registry, config: Mapping[str, Any]) -> TransformStage:
    """Builds the transform stage from the config's transformer list."""
    section: Mapping[str, Any] = config.get("transform") or {}
    return TransformStage(_build_refs(registry, "transformer", section.get("transformers", [])))


def build_persist_stage(registry: Registry, config: Mapping[str, Any]) -> PersistStage:
    """Builds the persist stage from the config's repository list."""
    section: Mapping[str, Any] = config.get("persist") or {}
    repositories = _build_refs(registry, "repository", section.get("repositories", []))
    if not repositories:
        raise ConfigError("pipeline has a persist stage but no repositories are configured")
    return PersistStage(repositories)


def build_discover_stage(config: Mapping[str, Any]) -> DiscoverStage:
    """Builds the discover stage from the config's `discover` section."""
    section: Mapping[str, Any] = config.get("discover") or {}
    if "next_url" not in section:
        raise ConfigError("pipeline has a discover stage but config has no `discover.next_url`")
    return DiscoverStage(
        next_url=section["next_url"],
        url_template=section.get("url_template"),
        max_new=int(section.get("max_new", 100)),
    )


def register_default_stages(registry: Registry, config: Mapping[str, Any]) -> None:
    """Registers all seven standard stages, wired from the given resolved config."""
    registry.register("stage", "fetch", lambda: build_fetch_stage(registry, config))
    registry.register("stage", "parse", lambda: build_parse_stage(registry, config))
    registry.register("stage", "discover", lambda: build_discover_stage(config))
    registry.register("stage", "extract", lambda: build_extract_stage(registry, config))
    registry.register("stage", "validate", lambda: build_validate_stage(registry, config))
    registry.register("stage", "transform", lambda: build_transform_stage(registry, config))
    registry.register("stage", "persist", lambda: build_persist_stage(registry, config))


def register_fetch_stage(registry: Registry, config: Mapping[str, Any]) -> None:
    """Registers just the config-wired fetch stage (used by fetch-only tests)."""
    registry.register("stage", "fetch", lambda: build_fetch_stage(registry, config))

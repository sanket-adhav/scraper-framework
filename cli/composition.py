"""The composition root: the one place that knows both core and components.

Registers every built-in component into a Registry and wires the config-driven
stages together. The CLI builds on this; core never imports components, so
this file is where the two sides meet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from components.extractors.spec_driven import SpecDrivenExtractor
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
from components.repositories.csv_repository import CsvRepository
from components.repositories.jsonl_repository import JsonlRepository
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
from core.errors.exceptions import ConfigError
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
    registry.register("extractor", "spec_driven", SpecDrivenExtractor)
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
    registry.register("repository", "jsonl", JsonlRepository)
    return registry


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
    """Builds the parse stage from the config's declared parser."""
    parser_name = config.get("parser")
    if not parser_name:
        raise ConfigError("pipeline has a parse stage but config declares no `parser`")
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


def register_default_stages(registry: Registry, config: Mapping[str, Any]) -> None:
    """Registers all six standard stages, wired from the given resolved config."""
    registry.register("stage", "fetch", lambda: build_fetch_stage(registry, config))
    registry.register("stage", "parse", lambda: build_parse_stage(registry, config))
    registry.register("stage", "extract", lambda: build_extract_stage(registry, config))
    registry.register("stage", "validate", lambda: build_validate_stage(registry, config))
    registry.register("stage", "transform", lambda: build_transform_stage(registry, config))
    registry.register("stage", "persist", lambda: build_persist_stage(registry, config))


def register_fetch_stage(registry: Registry, config: Mapping[str, Any]) -> None:
    """Registers just the config-wired fetch stage (used by fetch-only tests)."""
    registry.register("stage", "fetch", lambda: build_fetch_stage(registry, config))

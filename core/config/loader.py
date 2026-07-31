"""The layered config loader (plan2.md §9).

Layering: built-in defaults → environment file → plugin config → per-job
overrides; later layers win per key. Everything is validated at load time —
shape (pydantic), component names (registry), selector kinds vs document
capabilities, and no-plaintext-credentials. The result carries a SHA-256
fingerprint so every record can say exactly which settings produced it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from core.config.capability_check import check_spec_against_capabilities
from core.config.schema import ScraperConfigModel
from core.contracts.secrets_provider import SECRET_REF_PREFIX, SecretsProvider
from core.errors.exceptions import ConfigError
from core.registry.registry import Registry

ConfigLayer = Mapping[str, Any] | str | Path

_SECRET_KEY_HINTS = ("password", "passwd", "secret", "token", "api_key", "apikey", "credential")

# Keys whose *name* contains a credential hint but whose value is structurally
# never a secret. A login-capable fetcher has to name the field it types into
# (`password_selector: input[name=...]`); that is a CSS selector, not a
# credential. The suffix must match exactly so `password_selector` is exempt
# while `password`, `password_value`, or `selector_password` are not.
_SECRET_KEY_EXEMPT_SUFFIXES = ("_selector",)


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """The fully merged, validated config plus its fingerprint."""

    data: Mapping[str, Any]
    fingerprint: str


PresetDirs = str | Path | Sequence[str | Path] | None


def load_config(
    layers: Sequence[ConfigLayer],
    *,
    presets_dir: PresetDirs = None,
    registry: Registry | None = None,
    secrets: Any = None,
) -> ResolvedConfig:
    """Merges the layers (later wins per key), validates everything, and returns
    the resolved config with its fingerprint. Raises ConfigError on any problem."""
    merged: dict[str, Any] = {}
    for layer in layers:
        data = _read_layer(layer)
        data = _expand_preset(data, presets_dir)
        merged = _deep_merge(merged, data)

    model = _validate_shape(merged)
    _reject_plaintext_secrets(merged)
    if registry is not None:
        _validate_names(model, registry)
        _validate_capabilities(model, registry)

    fingerprint = hashlib.sha256(
        json.dumps(merged, sort_keys=True, default=str).encode()
    ).hexdigest()
    if secrets is not None:
        merged = resolve_secret_refs(merged, secrets)
    return ResolvedConfig(data=merged, fingerprint=fingerprint)


def resolve_secret_refs(value: Any, provider: SecretsProvider) -> Any:
    """Returns a copy of the value with every `secret://` string resolved to its
    real secret. Called at component-build time — the fingerprint never sees secrets."""
    if isinstance(value, str) and value.startswith(SECRET_REF_PREFIX):
        return provider.resolve(value)
    if isinstance(value, Mapping):
        return {k: resolve_secret_refs(v, provider) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_secret_refs(v, provider) for v in value]
    return value


def _read_layer(layer: ConfigLayer) -> dict[str, Any]:
    """Accepts a dict or a YAML file path and returns the layer as a dict."""
    if isinstance(layer, Mapping):
        return dict(layer)
    path = Path(layer)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"config file {path} must contain a mapping, got {type(loaded).__name__}")
    return loaded


def _preset_search_path(presets_dir: PresetDirs) -> list[Path]:
    """Normalises the presets argument into an ordered search path.

    Accepting a sequence lets a project's own presets directory shadow the ones
    shipped inside the package, without either side knowing about the other.
    """
    if presets_dir is None:
        return []
    if isinstance(presets_dir, str | Path):
        return [Path(presets_dir)]
    return [Path(p) for p in presets_dir]


def _expand_preset(data: dict[str, Any], presets_dir: PresetDirs) -> dict[str, Any]:
    """If the layer names a preset, loads it and merges the layer on top of it."""
    preset_name = data.pop("preset", None)
    if preset_name is None:
        return data
    search = _preset_search_path(presets_dir)
    if not search:
        raise ConfigError(f"config references preset {preset_name!r} but no presets dir is set")
    for directory in search:
        candidate = directory / f"{preset_name}.yaml"
        if candidate.exists():
            return _deep_merge(_read_layer(candidate), data)
    looked_in = ", ".join(str(d) for d in search)
    available = sorted({p.stem for d in search if d.is_dir() for p in d.glob("*.yaml")})
    raise ConfigError(
        f"preset {preset_name!r} not found (looked in: {looked_in}); "
        f"available presets: {available or 'none'}"
    )


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merges override into base: dicts merge per key, everything else is replaced."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _validate_shape(merged: Mapping[str, Any]) -> ScraperConfigModel:
    """Runs the pydantic schema over the merged config, converting failures to ConfigError."""
    try:
        return ScraperConfigModel.model_validate(merged)
    except PydanticValidationError as err:
        raise ConfigError(f"invalid config shape:\n{err}") from err


def _reject_plaintext_secrets(value: Any, path: str = "") -> None:
    """Fails the load if any credential-looking key holds a plaintext value
    instead of a `secret://` reference."""
    if isinstance(value, Mapping):
        for key, sub in value.items():
            key_path = f"{path}.{key}" if path else str(key)
            lowered = str(key).lower()
            if (
                isinstance(sub, str)
                and sub
                and not sub.startswith(SECRET_REF_PREFIX)
                and any(hint in lowered for hint in _SECRET_KEY_HINTS)
                and not lowered.endswith(_SECRET_KEY_EXEMPT_SUFFIXES)
            ):
                raise ConfigError(
                    f"config key {key_path!r} looks like a credential but is plaintext; "
                    f"use a {SECRET_REF_PREFIX} reference instead"
                )
            _reject_plaintext_secrets(sub, key_path)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _reject_plaintext_secrets(item, f"{path}[{i}]")


def _validate_names(model: ScraperConfigModel, registry: Registry) -> None:
    """Checks every configured component name resolves in the registry."""
    if not model.pipeline:
        raise ConfigError("config has no pipeline; a non-empty stage list is required")
    for stage_name in model.pipeline:
        registry.factory("stage", stage_name)
    for mw_name in model.middleware:
        registry.factory("middleware", mw_name)
    if model.parser is not None:
        registry.factory("parser", model.parser)
    if model.extractor is not None:
        registry.factory("extractor", model.extractor)
    sections = [
        ("validator", model.validate_.validators if model.validate_ else []),
        ("transformer", model.transform_.transformers if model.transform_ else []),
        ("repository", model.persist_.repositories if model.persist_ else []),
    ]
    for kind, refs in sections:
        for ref in refs:
            registry.factory(kind, ref.name)


def _validate_capabilities(model: ScraperConfigModel, registry: Registry) -> None:
    """Checks every spec field's selector kind against the configured parser's
    document capabilities (plan2.md §5) — the 2 a.m. error, moved to startup."""
    if model.extract is None or model.parser is None:
        return
    parser_factory = registry.factory("parser", model.parser)
    document_type = getattr(parser_factory, "document_type", None)
    if document_type is None:
        raise ConfigError(
            f"parser {model.parser!r} does not declare document_type; cannot validate spec"
        )
    field_kinds = {
        name: spec.kind
        for name, spec in model.extract.spec.items()
        if spec.against is None  # fields matched against e.g. the URL don't query the document
    }
    check_spec_against_capabilities(
        field_kinds, document_type.capabilities, document_type.__name__
    )

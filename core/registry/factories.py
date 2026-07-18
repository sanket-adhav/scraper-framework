"""Builds configured component instances out of registry factories."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.errors.exceptions import ConfigError
from core.registry.registry import Registry


def build_component(
    registry: Registry, kind: str, name: str, options: Mapping[str, Any] | None = None
) -> Any:
    """Creates one component instance, passing its config options as keyword arguments."""
    factory = registry.factory(kind, name)
    opts = dict(options or {})
    try:
        return factory(**opts)
    except TypeError as err:
        raise ConfigError(f"cannot build {kind} {name!r} with options {opts}: {err}") from err

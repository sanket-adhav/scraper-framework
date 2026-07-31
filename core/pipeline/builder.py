"""Builds a pipeline (ordered Stage instances) from a config name list via the registry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.contracts.stage import Stage
from core.registry.factories import build_component
from core.registry.registry import Registry


def build_pipeline(
    stage_names: Sequence[str],
    registry: Registry,
    stage_options: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[Stage]:
    """Resolves each configured stage name into a Stage instance, in order."""
    options = stage_options or {}
    return [
        build_component(registry, "stage", name, options.get(name)) for name in stage_names
    ]

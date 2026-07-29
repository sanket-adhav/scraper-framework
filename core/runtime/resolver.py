"""The JobResolver: turns (plugin, runtime params) into a fully rendered config.

This is the single seam between "what the caller asked for" and "what the engine
executes". Its responsibilities, and nothing more:

    load plugin  →  validate params against the plugin's contract  →
    apply defaults  →  render placeholders  →  hand back a resolved config

The engine is handed only the resolved configuration and never learns that
parameters existed. All rendering lives here, outside the engine, exactly as the
architecture requires.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.plugin.manager import PluginManager
from core.registry.registry import Registry
from core.runtime.params import validate_params
from core.runtime.template import render_template


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeConfig:
    """The output of one resolution: the plugin, the parameters that shaped it,
    and the rendered config the engine will run. Plain data, no logic."""

    plugin: str
    params: Mapping[str, Any]
    config: Mapping[str, Any]


class JobResolver:
    """Resolves a caller request into a runnable config using loaded plugins."""

    def __init__(self, manager: PluginManager) -> None:
        """Remembers a PluginManager that has already loaded the plugin folder."""
        self._manager = manager

    @classmethod
    def from_directory(cls, plugins_dir: Path, registry: Registry) -> JobResolver:
        """Convenience builder: loads every plugin under `plugins_dir` (registering
        any contributed components into `registry`) and returns a ready resolver."""
        manager = PluginManager(registry)
        manager.load_all(plugins_dir)
        return cls(manager)

    def resolve(
        self, plugin: str, params: Mapping[str, Any] | None = None
    ) -> ResolvedRuntimeConfig:
        """Produces a fully resolved config for one plugin and one parameter set.

        Raises PluginError if the plugin is not loaded, or ParamError if the
        parameters violate the plugin's declared contract."""
        loaded = self._manager.get(plugin)
        contract = loaded.manifest.params
        resolved_params = validate_params(contract, params or {})
        rendered = render_template(
            dict(loaded.config), resolved_params, declared=set(contract)
        )
        return ResolvedRuntimeConfig(
            plugin=plugin, params=resolved_params, config=rendered
        )

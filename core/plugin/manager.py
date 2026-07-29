"""The plugin lifecycle manager (plan2.md §10).

discover → validate manifest → conformance-check contributed components →
register (namespaced) → merge config. A plugin failing ANY step is quarantined
with the reason logged; it never crashes the system or affects other plugins.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.contracts import (
    Document,
    Extractor,
    Fetcher,
    LoginProvider,
    Middleware,
    Parser,
    Repository,
    Stage,
    Transformer,
    Validator,
)
from core.errors.exceptions import PluginError
from core.plugin.discovery import PluginCandidate, scan_directory
from core.plugin.manifest import PluginManifest, load_manifest
from core.registry.registry import Registry

logger = logging.getLogger("scraper.plugins")

_PROTOCOLS: Mapping[str, type] = {
    "fetcher": Fetcher,
    "parser": Parser,
    "document": Document,
    "extractor": Extractor,
    "validator": Validator,
    "transformer": Transformer,
    "repository": Repository,
    "middleware": Middleware,
    "stage": Stage,
    "login_provider": LoginProvider,
}


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    """A plugin that passed every lifecycle step, with its merged config."""

    manifest: PluginManifest
    path: Path
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QuarantinedPlugin:
    """A plugin that failed a lifecycle step: kept aside, visible, never fatal."""

    name: str
    path: Path
    reason: str


class PluginManager:
    """Loads plugins from a directory, quarantining anything broken."""

    def __init__(self, registry: Registry) -> None:
        """Remembers the registry that contributed components get registered into."""
        self._registry = registry
        self.loaded: list[LoadedPlugin] = []
        self.quarantined: list[QuarantinedPlugin] = []

    def load_all(self, root: Path) -> None:
        """Runs the full lifecycle for every plugin folder under `root`."""
        seen_names: set[str] = set()
        for candidate in scan_directory(root):
            try:
                plugin = self._load_one(candidate, seen_names)
            except Exception as err:  # noqa: BLE001 — quarantine, never crash the system
                logger.warning("plugin %s quarantined: %s", candidate.name, err)
                self.quarantined.append(
                    QuarantinedPlugin(name=candidate.name, path=candidate.path, reason=str(err))
                )
            else:
                seen_names.add(plugin.manifest.name)
                self.loaded.append(plugin)

    def get(self, plugin_name: str) -> LoadedPlugin:
        """Returns one loaded plugin (manifest + merged config), by manifest name."""
        for plugin in self.loaded:
            if plugin.manifest.name == plugin_name:
                return plugin
        raise PluginError(f"no loaded plugin named {plugin_name!r}")

    def config_for(self, plugin_name: str) -> Mapping[str, Any]:
        """Returns the merged config of one loaded plugin, by manifest name."""
        return self.get(plugin_name).config

    def _load_one(self, candidate: PluginCandidate, seen_names: set[str]) -> LoadedPlugin:
        """Manifest → collision check → components → config, for one candidate."""
        manifest = load_manifest(candidate.manifest_path)
        if manifest.name in seen_names:
            raise PluginError(f"plugin name {manifest.name!r} is already loaded (collision)")
        self._register_components(manifest, candidate.path)
        config = self._merge_config(manifest, candidate.path)
        return LoadedPlugin(manifest=manifest, path=candidate.path, config=config)

    def _register_components(self, manifest: PluginManifest, path: Path) -> None:
        """Imports, conformance-checks, and registers each contributed component
        under the namespaced name '<plugin>.<component>'."""
        for kind, entries in manifest.components.items():
            protocol = _PROTOCOLS.get(kind)
            if protocol is None:
                raise PluginError(f"unknown component kind {kind!r}; known: {sorted(_PROTOCOLS)}")
            for comp_name, ref in entries.items():
                cls = _import_class(manifest.name, path, ref)
                _check_conformance(cls, protocol, kind, ref)
                self._registry.register(kind, f"{manifest.name}.{comp_name}", cls)

    def _merge_config(self, manifest: PluginManifest, path: Path) -> dict[str, Any]:
        """Merges the plugin's declared config files (later files win per key)."""
        merged: dict[str, Any] = {}
        for rel in manifest.config_files:
            file = path / rel
            if not file.is_file():
                raise PluginError(f"declared config file missing: {file}")
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise PluginError(f"config file {file} must be a mapping")
            merged.update(data)
        return merged


def _import_class(plugin_name: str, plugin_path: Path, ref: str) -> type:
    """Loads 'file.py:ClassName' from inside the plugin folder."""
    try:
        file_part, class_name = ref.split(":", 1)
    except ValueError as err:
        raise PluginError(f"component ref {ref!r} must look like 'file.py:ClassName'") from err
    module_file = plugin_path / file_part
    if not module_file.is_file():
        raise PluginError(f"component file missing: {module_file}")
    spec = importlib.util.spec_from_file_location(
        f"plugins.{plugin_name}.{module_file.stem}", module_file
    )
    if spec is None or spec.loader is None:
        raise PluginError(f"cannot import {module_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    obj = getattr(module, class_name, None)
    if not isinstance(obj, type):
        raise PluginError(f"{module_file} has no class named {class_name!r}")
    return obj


def _check_conformance(cls: type, protocol: type, kind: str, ref: str) -> None:
    """Instantiates the component and checks it satisfies its contract —
    the load-time slice of the contract suite (full suites run in CI)."""
    try:
        instance = cls()
    except Exception as err:  # noqa: BLE001 — any constructor failure quarantines
        raise PluginError(f"cannot construct {ref} with no arguments: {err}") from err
    if not isinstance(instance, protocol):
        raise PluginError(f"{ref} does not satisfy the {kind} contract ({protocol.__name__})")

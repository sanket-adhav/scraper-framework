"""Public Python API — the supported way to drive the framework in-process.

Use this instead of hand-assembling the engine. It is the same composition root
the CLI uses, so a scrape started from Python behaves identically to the same
scrape started from the terminal: the packaged default middleware stack, the
quarantine sink, and the secrets provider are all wired for you.

    from cli.api import run_scraper

    result = run_scraper("sebi_circulars", {"title": "Mutual Fund Regulations"})
    if not result.ok:
        raise SystemExit(f"{result.aborted} aborted, {result.quarantined} quarantined")

This module lives in `cli` rather than `core` on purpose. `core` sits at the
bottom of the import layering (see importlinter.ini) and may not import
`components`; anything that composes concrete fetchers, parsers and repositories
belongs at this level. The previous `core/api.py` violated that rule — and did
not import at all, because it pulled `JobResult` from the wrong module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cli.main import (
    _build_engine,
    _job_from_config,
    _load_validated,
    _resolve_plugin,
)
from core.engine.scraper_engine import JobResult
from core.plugin.manager import PluginManager
from core.registry.registry import Registry
from core.runtime.resolver import ResolvedRuntimeConfig

__all__ = [
    "DEFAULT_CONFIG_DIR",
    "DEFAULT_PLUGINS_DIR",
    "JobResult",
    "list_plugins",
    "resolve_plugin",
    "run_job_file",
    "run_scraper",
]

#: Where plugins and project config are looked for, relative to the process's
#: working directory. Both are overridable per call.
DEFAULT_PLUGINS_DIR = Path("plugins")
DEFAULT_CONFIG_DIR = Path("config")


def _dirs(plugins_dir: Path | str | None, config_dir: Path | str | None) -> tuple[Path, Path]:
    """Normalises the two directory arguments, applying the defaults."""
    return (
        Path(plugins_dir) if plugins_dir is not None else DEFAULT_PLUGINS_DIR,
        Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR,
    )


def run_scraper(
    plugin: str,
    params: Mapping[str, Any] | None = None,
    *,
    plugins_dir: Path | str | None = None,
    config_dir: Path | str | None = None,
    dry_run: bool = False,
    quarantine_dir: Path | str = "quarantine",
) -> JobResult:
    """Runs one plugin with runtime parameters and returns the job outcome.

    Args:
        plugin: The plugin's `name:` from its plugin.yaml — not the folder name.
        params: Runtime parameters, validated against the plugin's declared
            contract. Unknown or mistyped values raise `ParamError`.
        plugins_dir: Directory holding plugin folders. Defaults to `./plugins`.
        config_dir: Project config overrides layered over the packaged defaults.
            Defaults to `./config`; it is fine for it not to exist.
        dry_run: Stop after `extract` and persist nothing.
        quarantine_dir: Where records that fail a stage are written for review.

    Returns:
        JobResult: counts for completed, aborted, quarantined and discarded
        requests. **Check `result.ok`** — a run where every record failed
        extraction still returns normally, with `quarantined` set.

    Raises:
        PluginError: the plugin is not loaded (wrong name, or it quarantined).
        ParamError: the parameters violate the plugin's contract.
        ConfigError: the resolved config failed a load-time check.
    """
    plugins_path, config_path = _dirs(plugins_dir, config_dir)
    _resolved, config, registry = _resolve_plugin(
        plugin, dict(params or {}), plugins_path, config_path
    )
    stages = _stage_names(list(config.data["pipeline"]), dry_run=dry_run)
    engine = _build_engine(config, registry, stages, quarantine_dir=quarantine_dir)
    return asyncio.run(engine.run(_job_from_config(config)))


def run_job_file(
    job_file: Path | str,
    *,
    config_dir: Path | str | None = None,
    dry_run: bool = False,
    quarantine_dir: Path | str = "quarantine",
) -> JobResult:
    """Runs a job/config YAML directly, for configs that take no runtime params."""
    _plugins_path, config_path = _dirs(None, config_dir)
    config, registry = _load_validated(Path(job_file), config_path)
    stages = _stage_names(list(config.data["pipeline"]), dry_run=dry_run)
    engine = _build_engine(config, registry, stages, quarantine_dir=quarantine_dir)
    return asyncio.run(engine.run(_job_from_config(config)))


def resolve_plugin(
    plugin: str,
    params: Mapping[str, Any] | None = None,
    *,
    plugins_dir: Path | str | None = None,
    config_dir: Path | str | None = None,
) -> ResolvedRuntimeConfig:
    """Resolves a plugin + params to its final config without running anything.

    Useful for previewing exactly what a parameter set would execute, and for
    asserting on resolved URLs in tests.
    """
    plugins_path, config_path = _dirs(plugins_dir, config_dir)
    resolved, _config, _registry = _resolve_plugin(
        plugin, dict(params or {}), plugins_path, config_path
    )
    return resolved


def list_plugins(plugins_dir: Path | str | None = None) -> PluginManager:
    """Loads every plugin under `plugins_dir` and returns the manager.

    The result exposes `.loaded` (each with its `.manifest`, including the
    `params` contract) and `.quarantined` (each with the `.reason` it failed),
    so callers can discover what is available and why something is missing.
    """
    plugins_path, _config_path = _dirs(plugins_dir, None)
    manager = PluginManager(Registry())
    manager.load_all(plugins_path)
    return manager


def _stage_names(pipeline: list[str], *, dry_run: bool) -> list[str]:
    """Truncates the stage list after `extract` when running a dry run."""
    if dry_run and "extract" in pipeline:
        return pipeline[: pipeline.index("extract") + 1]
    return pipeline

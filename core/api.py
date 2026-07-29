"""Public API for integrating the Scraper Framework into other Python systems.

This module provides the clean `run_scraper` entry point so external
applications (like Compliance Assist) can invoke the engine directly in-memory,
passing dynamic parameters without using the CLI or modifying YAML on disk.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cli.main import _build_engine, _job_from_config, _resolve_plugin
from core.models.job import JobResult

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = REPO_ROOT / "plugins"
CONFIG_DIR = REPO_ROOT / "config"


def run_scraper(
    plugin_name: str, 
    params: dict[str, Any] | None = None,
    plugins_dir: Path | str | None = None,
    config_dir: Path | str | None = None
) -> JobResult:
    """Runs a scraper plugin with the given dynamic parameters.

    Args:
        plugin_name: The name of the plugin (e.g. "sebi_circulars")
        params: A dictionary of parameters to inject (e.g. {"title": "..."})
        plugins_dir: Custom path to a directory containing plugins. Defaults to framework's internal plugins.
        config_dir: Custom path to a directory containing configs. Defaults to framework's internal configs.

    Returns:
        JobResult: Statistics about the completed scrape job. Data is
                   saved to the repositories defined in the plugin's persist stage.
    """
    params = params or {}
    
    # Use provided directories or fallback to the framework's default internal directories
    resolved_plugins_dir = Path(plugins_dir) if plugins_dir else PLUGINS_DIR
    resolved_config_dir = Path(config_dir) if config_dir else CONFIG_DIR
    
    # 1. Resolve plugin, validate params against its schema, and inject into config
    resolved_plugin, plugin_config, components_registry = _resolve_plugin(
        plugin_name, params, resolved_plugins_dir, resolved_config_dir
    )
    
    # 2. Build the execution engine pipeline
    engine = _build_engine(plugin_config, components_registry, list(plugin_config.data["pipeline"]))
    
    # 3. Formulate the Job and execute it asynchronously
    job = _job_from_config(plugin_config)
    
    # Run the event loop synchronously to block until done
    result = asyncio.run(engine.run(job))
    
    return result

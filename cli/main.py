"""The operator CLI (plan2.md §8): run, validate, dry-run, list-components.

Everything a scrape needs comes from YAML; the CLI only assembles and runs it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from cli.composition import default_registry, register_default_stages
from cli.scaffold import scaffold_plugin
from components.quarantine.file_sink import FileQuarantineSink
from core.config.loader import ConfigLayer, ResolvedConfig, load_config
from core.engine.job import ScrapeJob
from core.engine.scraper_engine import JobResult, ScraperEngine
from core.errors.exceptions import ConfigError, ScraperError
from core.errors.policy import policy_from_config
from core.models.scrape_request import ScrapeRequest
from core.pipeline.builder import build_pipeline
from core.pipeline.runner import PipelineRunner
from core.plugin.manager import PluginManager
from core.registry.registry import Registry

app = typer.Typer(help="Config-driven scraping framework.", no_args_is_help=True)


def _layers(job_file: Path | None, config_dir: Path) -> list[ConfigLayer]:
    """Builds the config layer list: shipped defaults first, the job file last."""
    layers: list[ConfigLayer] = []
    for default in ("pipeline.yaml", "middleware.yaml"):
        path = config_dir / default
        if path.exists():
            layers.append(path)
    if job_file is not None:
        layers.append(job_file)
    return layers


def _load_validated(job_file: Path | None, config_dir: Path) -> tuple[ResolvedConfig, Registry]:
    """Loads config in two passes: shape first, then full name/capability checks
    once the config-wired stages are registered."""
    layers = _layers(job_file, config_dir)
    presets = config_dir / "presets"
    config = load_config(layers, presets_dir=presets if presets.exists() else None)
    registry = default_registry()
    register_default_stages(registry, config.data)
    config = load_config(
        layers, presets_dir=presets if presets.exists() else None, registry=registry
    )
    return config, registry


def _build_engine(
    config: ResolvedConfig, registry: Registry, stage_names: list[str]
) -> ScraperEngine:
    """Assembles runner + engine for the given stage list."""
    stages = build_pipeline(stage_names, registry)
    quarantine_dir = str(config.data.get("quarantine_dir", "quarantine"))
    runner = PipelineRunner(
        stages,
        policy_from_config(config.data),
        timeouts=config.data.get("stage_timeouts", {}),
        quarantine=FileQuarantineSink(quarantine_dir),
    )
    return ScraperEngine(runner, config)


def _job_from_config(config: ResolvedConfig) -> ScrapeJob:
    """Builds the ScrapeJob from the config's `urls` list."""
    urls = config.data.get("urls") or []
    if not urls:
        raise ConfigError("config has no `urls` — nothing to scrape")
    return ScrapeJob(requests=tuple(ScrapeRequest(url=u) for u in urls))


def _echo_summary(result: JobResult) -> None:
    """Prints the one-line job outcome."""
    typer.echo(
        f"job {result.job_id}: {result.completed} completed, "
        f"{result.aborted} aborted, {result.quarantined} quarantined"
    )


@app.command()
def run(
    job_file: Path = typer.Argument(..., help="Job YAML (urls, spec, pipeline overrides)"),
    config_dir: Path = typer.Option(Path("config"), help="Directory with default YAMLs"),
) -> None:
    """Runs the full pipeline for a job file; exit 1 if any request aborted."""
    try:
        config, registry = _load_validated(job_file, config_dir)
        engine = _build_engine(config, registry, list(config.data["pipeline"]))
        result = asyncio.run(engine.run(_job_from_config(config)))
    except ScraperError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from err
    _echo_summary(result)
    if result.aborted:
        raise typer.Exit(code=1)


@app.command()
def validate(
    config_file: Path = typer.Argument(..., help="Config/job YAML to check"),
    config_dir: Path = typer.Option(Path("config"), help="Directory with default YAMLs"),
) -> None:
    """Runs every load-time check (shape, names, capabilities, secrets); exit 1 on failure.
    Designed to run in CI."""
    try:
        config, _ = _load_validated(config_file, config_dir)
    except ScraperError as err:
        typer.echo(f"invalid: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(f"ok (fingerprint {config.fingerprint[:12]})")


@app.command("dry-run")
def dry_run(
    job_file: Path = typer.Argument(..., help="Job YAML"),
    config_dir: Path = typer.Option(Path("config"), help="Directory with default YAMLs"),
) -> None:
    """Runs the pipeline through extract only, prints records, persists nothing."""
    try:
        config, registry = _load_validated(job_file, config_dir)
        names = list(config.data["pipeline"])
        names = names[: names.index("extract") + 1] if "extract" in names else names
        engine = _build_engine(config, registry, names)
        result = asyncio.run(engine.run(_job_from_config(config)))
    except ScraperError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from err
    for pipeline_result in result.results:
        record = pipeline_result.context.record
        if record is not None:
            typer.echo(json.dumps(dict(record.data), ensure_ascii=False, default=str))
    _echo_summary(result)


@app.command("list-components")
def list_components(
    plugins_dir: Path = typer.Option(Path("plugins"), help="Plugin folder to inspect"),
) -> None:
    """Lists every registered component by kind, plus plugin status (incl. quarantined)."""
    registry = default_registry()
    manager = PluginManager(registry)
    if plugins_dir.is_dir():
        manager.load_all(plugins_dir)
    for kind in registry.kinds():
        typer.echo(f"{kind}: {', '.join(registry.names(kind))}")
    typer.echo("stage: fetch, parse, discover, extract, validate, transform, persist (from config)")
    for plugin in manager.loaded:
        m = plugin.manifest
        typer.echo(f"plugin: {m.name} v{m.version} [{m.tier}] — ok")
    for bad in manager.quarantined:
        typer.echo(f"plugin: {bad.name} — QUARANTINED: {bad.reason}")


scaffold_app = typer.Typer(help="Generate boilerplate.", no_args_is_help=True)
app.add_typer(scaffold_app, name="scaffold")


@scaffold_app.command("new-plugin")
def new_plugin(
    name: str = typer.Argument(..., help="Plugin name (lowercase identifier)"),
    plugins_dir: Path = typer.Option(Path("plugins"), help="Where plugin folders live"),
) -> None:
    """Creates a working plugin skeleton that passes `scraper validate` immediately."""
    try:
        root = scaffold_plugin(name, plugins_dir)
    except FileExistsError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(f"created {root}")
    typer.echo(f"next: scraper validate {root / 'config' / 'extraction.yaml'}")


if __name__ == "__main__":
    app()

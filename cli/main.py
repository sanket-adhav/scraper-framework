"""The operator CLI (plan2.md §8): run, validate, dry-run, list-components.

Everything a scrape needs comes from YAML; the CLI only assembles and runs it.
"""
# handles terminal commands for user interface
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import dotenv
import typer

from cli.composition import build_event_bus, default_registry, register_default_stages
from cli.scaffold import scaffold_plugin
from components.quarantine.file_sink import FileQuarantineSink
from components.secrets.env_provider import EnvSecretsProvider
from core.config.loader import ConfigLayer, ResolvedConfig, load_config
from core.engine.scraper_engine import JobResult, ScraperEngine
from core.errors.exceptions import ConfigError, ScraperError
from core.errors.policy import policy_from_config
from core.models.job import ScrapeJob
from core.models.scrape_request import ScrapeRequest
from core.pipeline.builder import build_pipeline
from core.pipeline.runner import PipelineRunner
from core.plugin.manager import PluginManager
from core.registry.registry import Registry
from core.runtime.resolver import JobResolver, ResolvedRuntimeConfig

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
    dotenv.load_dotenv()
    layers = _layers(job_file, config_dir)
    presets = config_dir / "presets"

    provider = EnvSecretsProvider()
    presets_dir = presets if presets.exists() else None
    config = load_config(layers, presets_dir=presets_dir, secrets=provider)

    registry = default_registry()
    register_default_stages(registry, config.data)

    config = load_config(
        layers, presets_dir=presets_dir, registry=registry, secrets=provider
    )
    return config, registry


def _parse_params(
    param: list[str] | None,
    params_json: str | None = None,
    params_file: Path | None = None,
) -> dict[str, object]:
    """Turns a params file, a `--params-json` string, and `--param key=value` pairs
    into one dict. Precedence low→high: file, then JSON, then key=value pairs, so a
    quick `-p` on the command line can override a value from a saved params file."""
    parsed: dict[str, object] = {}
    if params_file is not None:
        parsed.update(_load_params_file(params_file))
    if params_json:
        try:
            loaded = json.loads(params_json)
        except json.JSONDecodeError as err:
            raise ConfigError(f"--params-json is not valid JSON: {err}") from err
        if not isinstance(loaded, dict):
            raise ConfigError("--params-json must be a JSON object")
        parsed.update(loaded)
    for item in param or []:
        if "=" not in item:
            raise ConfigError(f"--param must be key=value, got {item!r}")
        key, value = item.split("=", 1)
        parsed[key.strip()] = value
    return parsed


def _load_params_file(path: Path) -> dict[str, object]:
    """Reads a YAML or JSON file holding a flat mapping of param name → value."""
    if not path.exists():
        raise ConfigError(f"params file not found: {path}")
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"params file {path} must contain a mapping of param: value")
    return dict(loaded)


def _resolve_plugin(
    plugin: str,
    params: dict[str, object],
    plugins_dir: Path,
    config_dir: Path,
) -> tuple[ResolvedRuntimeConfig, ResolvedConfig, Registry]:
    """Resolves a plugin + runtime params into a validated, engine-ready config.

    This is the dynamic-parameter execution flow: load plugin → validate params
    → render placeholders (JobResolver) → layer under the shipped defaults →
    run every load-time check. The engine only ever sees the resolved result."""
    dotenv.load_dotenv()
    registry = default_registry()
    resolver = JobResolver.from_directory(plugins_dir, registry)
    resolved = resolver.resolve(plugin, params)

    presets = config_dir / "presets"
    presets_dir = presets if presets.exists() else None
    provider = EnvSecretsProvider()
    layers: list[ConfigLayer] = _layers(None, config_dir) + [dict(resolved.config)]

    register_default_stages(registry, load_config(layers, presets_dir=presets_dir).data)
    config = load_config(
        layers, presets_dir=presets_dir, registry=registry, secrets=provider
    )
    return resolved, config, registry


def _build_engine(
    config: ResolvedConfig,
    registry: Registry,
    stage_names: list[str],
    *,
    discovered_sink: object = None,
) -> ScraperEngine:
    """Assembles runner + engine for the given stage list, with logging + metrics
    listeners attached to the event bus. A discovered_sink switches on queue mode."""
    stages = build_pipeline(stage_names, registry)
    quarantine_dir = str(config.data.get("quarantine_dir", "quarantine"))
    bus, _ = build_event_bus()
    runner = PipelineRunner(
        stages,
        policy_from_config(config.data),
        timeouts=config.data.get("stage_timeouts", {}),
        quarantine=FileQuarantineSink(quarantine_dir),
        bus=bus,
    )
    return ScraperEngine(runner, config, bus=bus, discovered_sink=discovered_sink)  # type: ignore[arg-type]


def _queue_dsn(config: ResolvedConfig) -> str:
    """Resolves the queue's Postgres DSN from config `queue.dsn` or DATABASE_URL."""
    queue_cfg = config.data.get("queue") or {}
    dsn = queue_cfg.get("dsn") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise ConfigError(
            "worker mode needs a Postgres queue: set `queue.dsn` or DATABASE_URL"
        )
    return str(dsn)


def _job_from_config(config: ResolvedConfig) -> ScrapeJob:
    """Builds the ScrapeJob from the config's `urls` list."""
    urls = config.data.get("urls") or []
    if not urls:
        raise ConfigError("config has no `urls` — nothing to scrape")
    return ScrapeJob(requests=tuple(ScrapeRequest(url=u) for u in urls))


def _echo_summary(result: JobResult) -> None:
    """Prints the one-line job outcome."""
    msg = (
        f"job {result.job_id}: {result.completed} completed, "
        f"{result.aborted} aborted, {result.quarantined} quarantined"
    )
    if result.discarded:
        msg += f", {result.discarded} discarded (filtered)"
    typer.echo(msg)


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


@app.command("run-plugin")
def run_plugin(
    plugin: str = typer.Argument(..., help="Plugin name, e.g. sebi_circulars"),
    param: list[str] = typer.Option(
        None, "--param", "-p", help="Runtime param as key=value (repeatable)"
    ),
    params_file: Path = typer.Option(
        None, "--params-file", "-f", help="YAML/JSON file of param: value pairs"
    ),
    params_json: str = typer.Option(
        None, "--params-json", help="Runtime params as a JSON object"
    ),
    plugins_dir: Path = typer.Option(Path("plugins"), help="Where plugin folders live"),
    config_dir: Path = typer.Option(Path("config"), help="Directory with default YAMLs"),
) -> None:
    """Runs a plugin with runtime parameters — no YAML edit needed.

    Pass params from a file, or inline, or both (inline overrides the file):

        scraper run-plugin sebi_circulars -f jobs/sif.yaml
        scraper run-plugin sebi_circulars -p title="Mutual Fund Regulations"
        scraper run-plugin sebi_circulars            # scrape everything
    """
    try:
        params = _parse_params(param, params_json, params_file)
        resolved, config, registry = _resolve_plugin(plugin, params, plugins_dir, config_dir)
        typer.echo(f"resolved {plugin} with params {dict(resolved.params) or '{}'}")
        engine = _build_engine(config, registry, list(config.data["pipeline"]))
        result = asyncio.run(engine.run(_job_from_config(config)))
    except ScraperError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from err
    _echo_summary(result)
    if result.aborted:
        raise typer.Exit(code=1)


@app.command("resolve")
def resolve(
    plugin: str = typer.Argument(..., help="Plugin name, e.g. sebi_circulars"),
    param: list[str] = typer.Option(
        None, "--param", "-p", help="Runtime param as key=value (repeatable)"
    ),
    params_file: Path = typer.Option(
        None, "--params-file", "-f", help="YAML/JSON file of param: value pairs"
    ),
    params_json: str = typer.Option(
        None, "--params-json", help="Runtime params as a JSON object"
    ),
    plugins_dir: Path = typer.Option(Path("plugins"), help="Where plugin folders live"),
    config_dir: Path = typer.Option(Path("config"), help="Directory with default YAMLs"),
) -> None:
    """Resolves a plugin + params to its final config and prints it — no scrape.
    Use it to preview exactly what the engine would run for a given parameter set."""
    try:
        params = _parse_params(param, params_json, params_file)
        _resolved, config, _registry = _resolve_plugin(plugin, params, plugins_dir, config_dir)
    except ScraperError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(json.dumps(dict(config.data), indent=2, ensure_ascii=False, default=str))


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


@app.command()
def submit(
    job_file: Path = typer.Argument(..., help="Job YAML whose seed URLs to enqueue"),
    config_dir: Path = typer.Option(Path("config"), help="Directory with default YAMLs"),
) -> None:
    """Enqueues a job's seed URLs onto the Postgres queue for workers to pick up."""
    from components.queue.postgres_queue import PostgresQueue

    try:
        config, _ = _load_validated(job_file, config_dir)
        queue = PostgresQueue(_queue_dsn(config))
        job = _job_from_config(config)
        asyncio.run(queue.submit(job))
    except ScraperError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(f"submitted job {job.job_id} ({len(job.requests)} seed requests)")


@app.command()
def worker(
    job_file: Path = typer.Argument(None, help="Optional job YAML to enqueue before working"),
    config_dir: Path = typer.Option(Path("config"), help="Directory with default YAMLs"),
    once: bool = typer.Option(False, help="Drain the queue and exit (else run forever)"),
) -> None:
    """Runs a queue worker: the SAME engine, but jobs come from the Postgres queue
    and discovered requests go back to it — config/flag only, no code change."""
    from components.queue.postgres_queue import PostgresQueue
    from core.engine.worker import Worker, queue_discovered_sink

    try:
        config, registry = _load_validated(job_file, config_dir)
        queue = PostgresQueue(_queue_dsn(config))
        engine = _build_engine(
            config, registry, list(config.data["pipeline"]),
            discovered_sink=queue_discovered_sink(queue),
        )
        worker_obj = Worker(queue, engine)

        async def _go() -> None:
            """Enqueues the seed job (if given) then drains or runs the worker loop."""
            if job_file is not None and config.data.get("urls"):
                await queue.submit(_job_from_config(config))
            stats = await (worker_obj.drain() if once else worker_obj.run_forever())
            typer.echo(f"worker done: {stats.acked} acked, {stats.nacked} nacked")

        asyncio.run(_go())
    except ScraperError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from err


quarantine_app = typer.Typer(help="Inspect and manage the needs-review pile.", no_args_is_help=True)
app.add_typer(quarantine_app, name="quarantine")


@quarantine_app.command("list")
def quarantine_list(
    quarantine_dir: Path = typer.Option(Path("quarantine"), help="Quarantine directory"),
) -> None:
    """Lists quarantined records (trace id, stage, error)."""
    records = FileQuarantineSink(quarantine_dir).read_all()
    if not records:
        typer.echo("quarantine is empty")
        return
    for rec in records:
        typer.echo(f"{rec.get('trace_id')} [{rec.get('stage')}] {rec.get('error_type')}: "
                   f"{str(rec.get('error_message'))[:80]}")
    typer.echo(f"— {len(records)} quarantined records")


@quarantine_app.command("inspect")
def quarantine_inspect(
    trace_id: str = typer.Argument(..., help="Trace id of the record to inspect"),
    quarantine_dir: Path = typer.Option(Path("quarantine"), help="Quarantine directory"),
) -> None:
    """Prints the full snapshot of one quarantined record."""
    for rec in FileQuarantineSink(quarantine_dir).read_all():
        if rec.get("trace_id") == trace_id:
            typer.echo(json.dumps(rec, indent=2, ensure_ascii=False, default=str))
            return
    typer.echo(f"no quarantined record with trace_id {trace_id}", err=True)
    raise typer.Exit(code=1)


@quarantine_app.command("retry")
def quarantine_retry(
    plugin: str = typer.Option(None, help="Only re-queue records from this plugin"),
    config_dir: Path = typer.Option(Path("config"), help="Directory with default YAMLs"),
    quarantine_dir: Path = typer.Option(Path("quarantine"), help="Quarantine directory"),
) -> None:
    """Re-queues quarantined records' URLs onto the Postgres queue after a fix, then
    clears them from the pile. Filter by --plugin to retry just one plugin's jobs."""
    from components.queue.postgres_queue import PostgresQueue

    sink = FileQuarantineSink(quarantine_dir)
    records = sink.read_all()
    retryable, kept = [], []
    for rec in records:
        snap = rec.get("context_snapshot") or {}
        url = snap.get("url") if isinstance(snap, dict) else None
        if url and (plugin is None or (isinstance(snap, dict) and snap.get("plugin") == plugin)):
            retryable.append((rec, url))
        else:
            kept.append(rec)
    if not retryable:
        typer.echo("nothing to retry")
        return
    try:
        dsn = os.environ.get("DATABASE_URL") or (
            (load_config([config_dir / "pipeline.yaml"]).data.get("queue") or {}).get("dsn")
        )
        if not dsn:
            raise ConfigError("retry needs a Postgres queue: set DATABASE_URL or queue.dsn")
        queue = PostgresQueue(str(dsn))

        async def _requeue() -> None:
            """Submits one job per retryable quarantined URL."""
            for _rec, url in retryable:
                await queue.submit(ScrapeJob(requests=(ScrapeRequest(url=str(url)),)))

        asyncio.run(_requeue())
    except ScraperError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from err
    sink.rewrite(kept)
    typer.echo(f"re-queued {len(retryable)} records; {len(kept)} remain in quarantine")


@quarantine_app.command("discard")
def quarantine_discard(
    quarantine_dir: Path = typer.Option(Path("quarantine"), help="Quarantine directory"),
) -> None:
    """Clears the entire needs-review pile."""
    n = FileQuarantineSink(quarantine_dir).discard_all()
    typer.echo(f"discarded {n} quarantined records")


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

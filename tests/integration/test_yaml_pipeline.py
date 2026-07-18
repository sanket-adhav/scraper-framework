"""Plan 03 DoD tests: a pipeline defined purely in YAML runs end-to-end with
stub stages; reordering/inserting stages is config-only; the fingerprint rides
on every Context; the shipped default config file is valid."""

from pathlib import Path

from core.config.loader import load_config
from core.engine.job import ScrapeJob
from core.engine.scraper_engine import ScraperEngine
from core.errors.policy import policy_from_config
from core.models import ScrapeRequest
from core.pipeline.builder import build_pipeline
from core.pipeline.runner import PipelineRunner
from core.registry.registry import Registry
from tests.fakes import DiscoverStage, FakeStage

REPO_ROOT = Path(__file__).parent.parent.parent


def make_registry(log: list[str]) -> Registry:
    """Registers stub stages (and a discover stage) that record their runs."""
    registry = Registry()
    for name in ["fetch", "parse", "extract", "validate", "transform", "persist"]:
        registry.register("stage", name, lambda n=name: FakeStage(n, log))
    registry.register(
        "stage", "discover", lambda: DiscoverStage(["https://site.example/page/2"])
    )
    return registry


def engine_from_yaml(yaml_path: Path, registry: Registry) -> ScraperEngine:
    """Builds a ready-to-run engine purely from a YAML config file."""
    config = load_config([yaml_path], registry=registry)
    stages = build_pipeline(config.data["pipeline"], registry)
    runner = PipelineRunner(
        stages,
        policy_from_config(config.data),
        timeouts=config.data.get("stage_timeouts", {}),
    )
    return ScraperEngine(runner, config)


class TestYamlPipeline:
    async def test_yaml_defined_pipeline_runs_end_to_end(self, tmp_path):
        (tmp_path / "job.yaml").write_text(
            "pipeline: [fetch, parse, extract, validate, transform, persist]\n"
        )
        log: list[str] = []
        engine = engine_from_yaml(tmp_path / "job.yaml", make_registry(log))
        result = await engine.run(ScrapeJob(requests=(ScrapeRequest(url="https://x.example"),)))
        assert result.completed == 1
        assert log == ["fetch", "parse", "extract", "validate", "transform", "persist"]

    async def test_reordering_and_inserting_stages_is_config_only(self, tmp_path):
        """Same registry, same code — a different YAML list changes the pipeline."""
        (tmp_path / "job.yaml").write_text("pipeline: [parse, fetch, discover, extract]\n")
        log: list[str] = []
        engine = engine_from_yaml(tmp_path / "job.yaml", make_registry(log))
        result = await engine.run(ScrapeJob(requests=(ScrapeRequest(url="https://x.example"),)))
        # discover spawned one child request, which ran through the pipeline too
        assert result.completed == 2
        # the logging stages ran in the YAML's order, twice (seed + child);
        # discover doesn't log, but its effect (the child run) is asserted above
        assert log == ["parse", "fetch", "extract"] * 2

    async def test_discovered_requests_fed_back_until_done(self, tmp_path):
        (tmp_path / "job.yaml").write_text("pipeline: [discover]\nengine: {max_requests: 10}\n")
        engine = engine_from_yaml(tmp_path / "job.yaml", make_registry([]))
        result = await engine.run(ScrapeJob(requests=(ScrapeRequest(url="https://x.example"),)))
        assert result.completed == 2  # seed + one child; children spawn nothing

    async def test_max_requests_caps_runaway_discovery(self, tmp_path):
        """Even a discover stage that always finds new pages cannot loop forever."""

        class EndlessDiscover(DiscoverStage):
            async def run(self, ctx):
                ctx.discovered_requests.append(ScrapeRequest(url="https://more.example"))
                return ctx

        registry = Registry()
        registry.register("stage", "discover", lambda: EndlessDiscover([]))
        (tmp_path / "job.yaml").write_text("pipeline: [discover]\nengine: {max_requests: 5}\n")
        engine = engine_from_yaml(tmp_path / "job.yaml", registry)
        result = await engine.run(ScrapeJob(requests=(ScrapeRequest(url="https://x.example"),)))
        assert result.completed == 5

    async def test_fingerprint_present_on_every_context(self, tmp_path):
        (tmp_path / "job.yaml").write_text("pipeline: [fetch]\n")
        log: list[str] = []
        registry = make_registry(log)
        config = load_config([tmp_path / "job.yaml"], registry=registry)
        engine = engine_from_yaml(tmp_path / "job.yaml", registry)
        result = await engine.run(
            ScrapeJob(
                requests=(
                    ScrapeRequest(url="https://a.example"),
                    ScrapeRequest(url="https://b.example"),
                )
            )
        )
        assert all(
            r.context.config_fingerprint == config.fingerprint and r.context.trace_id
            for r in result.results
        )

    def test_shipped_default_config_is_valid(self):
        """The repo's config/pipeline.yaml loads and its stage names all resolve."""
        config = load_config([REPO_ROOT / "config" / "pipeline.yaml"], registry=make_registry([]))
        assert config.data["pipeline"][0] == "fetch"
        assert config.fingerprint

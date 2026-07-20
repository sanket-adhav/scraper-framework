"""Plan 08 / Phase-2 exit tests: the third plugin runs green through public seams,
listeners run purely as bus subscribers (and killing one can't fail a scrape),
metrics dashboards get populated, and per-plugin error-policy override works."""

import json
from pathlib import Path

from cli.composition import build_event_bus, default_registry, register_default_stages
from components.listeners.metrics_listener import MetricsListener
from core.config.loader import load_config
from core.engine.job import ScrapeJob
from core.engine.scraper_engine import ScraperEngine
from core.errors.policy import policy_from_config
from core.events.bus import EventBus
from core.models import ScrapeRequest
from core.pipeline.builder import build_pipeline
from core.pipeline.runner import PipelineRunner

REPO_ROOT = Path(__file__).parent.parent.parent


async def run_config(config_data: dict, *, bus: EventBus | None = None) -> ScraperEngine:
    """Runs a full scrape from a config dict, returning the engine for inspection."""
    registry = default_registry()
    register_default_stages(registry, config_data)
    config = load_config([config_data], registry=registry)
    stages = build_pipeline(config.data["pipeline"], registry)
    bus = bus or EventBus()
    runner = PipelineRunner(stages, policy_from_config(config.data), bus=bus)
    engine = ScraperEngine(runner, config, bus=bus)
    job = ScrapeJob(requests=tuple(ScrapeRequest(url=u) for u in config.data["urls"]))
    engine._last = await engine.run(job)  # type: ignore[attr-defined]
    return engine


def news_feed_config(out_path: Path) -> dict:
    """Loads the news_feed plugin config with a tmp output path overlay."""
    base = load_config(
        [REPO_ROOT / "plugins" / "news_feed" / "config" / "extraction.yaml"]
    ).data
    cfg = dict(base)
    cfg["fetcher_options"] = {"root": str(REPO_ROOT / "plugins" / "news_feed" / "fixtures")}
    cfg["persist"] = {
        "repositories": [
            {"name": "jsonl", "options": {"path": str(out_path), "mode": "upsert",
                                          "key_fields": ["sku"]}}
        ]
    }
    return cfg


class TestThirdPluginGreen:
    async def test_news_feed_paginates_all_three_pages(self, tmp_path):
        """Zero core/components changes by the plugin author — XML + pagination
        + date/enum transforms, all config."""
        out = tmp_path / "news.jsonl"
        engine = await run_config(news_feed_config(out))
        result = engine._last  # type: ignore[attr-defined]
        assert result.completed == 3 and result.aborted == 0
        rows = {json.loads(line)["sku"]: json.loads(line) for line in out.read_text().splitlines()}
        assert set(rows) == {"B0AURX2HDX", "B0NIMBUSPD", "B0LUMENLMP"}
        assert rows["B0AURX2HDX"]["published"] == "2026-07-17"  # date normalized
        assert rows["B0AURX2HDX"]["category"] == "audio"  # enum mapped
        assert rows["B0LUMENLMP"]["category"] == "home_goods"
        assert all(r["source"] == "shopverse_feed" for r in rows.values())


class TestListenersAsSubscribers:
    async def test_metrics_populated_from_a_real_run(self, tmp_path):
        """DoD: block-rate & per-field validation dashboards get data — the metrics
        listener counts a real scrape's events."""
        metrics = MetricsListener()
        bus, _ = build_event_bus(metrics=metrics)
        out = tmp_path / "news.jsonl"
        await run_config(news_feed_config(out), bus=bus)
        assert metrics.value(metrics.records_saved, plugin="news_feed") == 3
        assert metrics.value(metrics.records_extracted, plugin="news_feed") == 3

    async def test_killing_a_listener_cannot_fail_a_scrape(self, tmp_path):
        """DoD: a listener that always crashes must not fail the scrape."""
        bus = EventBus()

        def exploding(event):
            raise RuntimeError("listener down")

        bus.subscribe("*", exploding)
        out = tmp_path / "news.jsonl"
        engine = await run_config(news_feed_config(out), bus=bus)
        assert engine._last.completed == 3  # type: ignore[attr-defined]
        assert bus.listener_errors > 0  # it did crash, repeatedly — and was isolated


class TestPerPluginErrorPolicy:
    def test_plugin_config_overrides_error_policy(self):
        """DoD: a plugin's error_policy merges over the framework default from
        config alone — news_feed makes transform failures SKIP."""
        base = {"error_policy": {"default": "abort", "stages": {"fetch": {"FetchError": "retry"}}}}
        plugin = load_config(
            [REPO_ROOT / "plugins" / "news_feed" / "config" / "extraction.yaml"]
        ).data
        merged = load_config([base, plugin]).data
        policy = policy_from_config(merged)
        from core.contracts.stage import ErrorAction
        from core.errors.exceptions import TransformError

        # plugin override present...
        assert policy.action_for("transform", TransformError("x")) is ErrorAction.SKIP
        # ...and the base policy still there
        from core.errors.exceptions import FetchError

        assert policy.action_for("fetch", FetchError("x")) is ErrorAction.RETRY

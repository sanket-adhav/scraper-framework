"""Plan 07 DoD (config-level): swapping fetcher http→playwright is config-only and
downstream can't tell; tier presets select the full middleware stack from YAML."""

from pathlib import Path

from cli.composition import build_fetch_stage, default_registry
from components.fetchers.playwright_fetcher import PlaywrightFetcher
from core.config.loader import load_config
from core.models import ScrapeRequest
from core.pipeline.context import Context
from tests.fake_browser import FakeBrowser, fake_browser_factory
from tests.helpers import FIXTURES_DIR

REPO_ROOT = Path(__file__).parent.parent.parent
PRESETS = REPO_ROOT / "core" / "defaults" / "presets"


def ctx(url: str) -> Context:
    """Builds a context carrying one request for the fetch stage."""
    return Context(trace_id="t", config={}, config_fingerprint="fp", request=ScrapeRequest(url=url))


class TestFetcherSwapIsConfigOnly:
    async def test_http_to_playwright_by_config_downstream_identical(self):
        """The same job config, only `fetcher:` changed, yields the same Response
        shape — the stage/pipeline can't tell which fetcher ran."""
        registry = default_registry()
        # register a browser-backed playwright variant (fake browser = offline)
        browser = FakeBrowser(pages={"https://x.example": "<html><body>rendered</body></html>"})
        registry.register(
            "fetcher", "playwright_test",
            lambda: PlaywrightFetcher(browser_factory=fake_browser_factory(browser)),
        )

        stage = build_fetch_stage(registry, {"fetcher": "playwright_test", "middleware": []})
        result = await stage.run(ctx("https://x.example"))
        assert result.response is not None
        assert result.response.status == 200
        assert b"rendered" in result.response.body

    async def test_local_file_still_works_unchanged(self):
        registry = default_registry()
        stage = build_fetch_stage(
            registry,
            {
                "fetcher": "local_file",
                "fetcher_options": {"root": str(FIXTURES_DIR)},
                "middleware": [],
            },
        )
        result = await stage.run(ctx("file://sample_product.html"))
        assert result.response is not None and b"Aurora X2" in result.response.body


class TestTierPresets:
    def test_defended_preset_selects_full_stack(self):
        """A plugin that says `preset: tier_defended` gets the defended middleware
        list — composition-only, no code."""
        config = load_config(
            [{"preset": "tier_defended", "parser": "html"}], presets_dir=PRESETS
        )
        mw = config.data["middleware"]
        assert "circuit_breaker" in mw
        assert "ua_rotation" in mw
        assert "cost_tracker" in mw
        assert mw.index("retry") < mw.index("rate_limit")  # retries still consume tokens

    def test_hostile_preset_includes_proxy_rotation(self):
        config = load_config([{"preset": "tier_hostile"}], presets_dir=PRESETS)
        assert "proxy_rotation" in config.data["middleware"]

    def test_open_preset_is_minimal(self):
        config = load_config([{"preset": "tier_open"}], presets_dir=PRESETS)
        assert "proxy_rotation" not in config.data["middleware"]
        assert "circuit_breaker" not in config.data["middleware"]

    def test_all_preset_middleware_names_resolve(self):
        """Every middleware named in every tier preset is a registered component."""
        registry = default_registry()
        for preset in ("tier_open", "tier_defended", "tier_hostile"):
            config = load_config([{"preset": preset}], presets_dir=PRESETS)
            for name in config.data["middleware"]:
                registry.factory("middleware", name)  # raises if unknown

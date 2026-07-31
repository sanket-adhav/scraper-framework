"""Plan 04 DoD tests: the fetch stage composed purely from YAML, middleware
reordering as a config-only change, the 200-CAPTCHA rejection, and the
retries-consume-tokens (no retry storms) property."""

from pathlib import Path

from cli.composition import build_fetch_stage, default_registry, register_fetch_stage
from components.middleware.rate_limiter import RateLimiterMiddleware
from core.config.loader import load_config
from core.errors.exceptions import FetchError
from core.errors.policy import ErrorPolicy
from core.models import Response, ScrapeRequest
from core.pipeline.context import Context
from core.pipeline.runner import PipelineRunner, PipelineStatus
from tests.contract.test_middleware_contract import TagMiddleware
from tests.fakes import FakeStage
from tests.helpers import FIXTURES_DIR

REPO_ROOT = Path(__file__).parent.parent.parent
MIDDLEWARE_YAML = REPO_ROOT / "core" / "defaults" / "middleware.yaml"


def make_ctx(url: str) -> Context:
    """Builds a context carrying one request, ready for the fetch stage."""
    return Context(
        trace_id="t-fetch", config={}, config_fingerprint="fp",
        request=ScrapeRequest(url=url),
    )


def fast_options() -> dict:
    """Middleware options that keep the default stack instant in tests."""
    return {
        "middleware_options": {
            "rate_limit": {"rate": 10000.0, "burst": 100.0},
            "retry": {"max_attempts": 3, "base_delay_s": 0.0001, "max_delay_s": 0.001},
        }
    }


class TestYamlComposedStack:
    async def test_full_phase1_stack_from_yaml_fetches_a_file(self):
        """DoD: the fetch stage runs with the shipped middleware.yaml stack,
        composed purely from config — zero network involved."""
        config = load_config(
            [
                MIDDLEWARE_YAML,
                {"fetcher": "local_file", "fetcher_options": {"root": str(FIXTURES_DIR)}},
                fast_options(),
            ]
        )
        registry = default_registry()
        register_fetch_stage(registry, config.data)
        stage = registry.factory("stage", "fetch")()
        ctx = await stage.run(make_ctx("file://sample_product.html"))
        assert ctx.response is not None
        assert ctx.response.status == 200
        assert b"Aurora X2" in ctx.response.body

    async def test_reordering_middleware_is_config_only(self):
        """DoD: two configs that differ only in the middleware list order produce
        provably different execution orders — same code, same registry."""
        log: list[str] = []
        registry = default_registry()
        registry.register("middleware", "tag_a", lambda: TagMiddleware("a", log))
        registry.register("middleware", "tag_b", lambda: TagMiddleware("b", log))
        base = {"fetcher": "local_file", "fetcher_options": {"root": str(FIXTURES_DIR)}}

        stage = build_fetch_stage(
            registry, load_config([base, {"middleware": ["tag_a", "tag_b"]}]).data
        )
        await stage.run(make_ctx("file://sample_product.html"))
        first_order = list(log)

        log.clear()
        stage = build_fetch_stage(
            registry, load_config([base, {"middleware": ["tag_b", "tag_a"]}]).data
        )
        await stage.run(make_ctx("file://sample_product.html"))

        assert first_order == ["a:in", "b:in", "b:out", "a:out"]
        assert log == ["b:in", "a:in", "a:out", "b:out"]


class TestCaptchaNeverParsed:
    async def test_200_captcha_fixture_rejected_and_parse_never_runs(self):
        """DoD: a 200-status CAPTCHA page is rejected as blocked by the full
        YAML stack, the pipeline aborts, and the parse stage never executes."""
        config = load_config(
            [
                MIDDLEWARE_YAML,
                {"fetcher": "local_file", "fetcher_options": {"root": str(FIXTURES_DIR)}},
                fast_options(),
            ]
        )
        registry = default_registry()
        register_fetch_stage(registry, config.data)
        parse_log: list[str] = []
        pipeline = [
            registry.factory("stage", "fetch")(),
            FakeStage("parse", parse_log),
        ]
        result = await PipelineRunner(pipeline, ErrorPolicy()).run(
            make_ctx("file://blocks/captcha_200.html")
        )
        assert result.status is PipelineStatus.ABORTED
        assert isinstance(result.error, FetchError)
        assert result.error.blocked is True
        assert parse_log == []  # the poisoned page never reached the parser


class TestNoRetryStorms:
    async def test_every_retry_attempt_consumes_a_rate_limit_token(self):
        """DoD: retry wraps the rate limiter, so retries re-enter it — three
        attempts show up as three token acquisitions, never a free storm."""
        registry = default_registry()

        class FlakyTwice:
            """Fetcher that fails transiently twice, then succeeds."""

            failures = 2

            async def fetch(self, request: ScrapeRequest) -> Response:
                if type(self).failures > 0:
                    type(self).failures -= 1
                    raise FetchError("blip", transient=True)
                return Response(status=200)

        limiter = RateLimiterMiddleware(rate=10000.0, burst=100.0)
        registry.register("middleware", "counting_rate_limit", lambda: limiter)
        registry.register("fetcher", "flaky", FlakyTwice)

        config = load_config(
            [
                {
                    "fetcher": "flaky",
                    "middleware": ["retry", "counting_rate_limit"],  # §6 order: retry outside
                    "middleware_options": {
                        "retry": {"max_attempts": 3, "base_delay_s": 0.0001, "max_delay_s": 0.001}
                    },
                }
            ]
        )
        stage = build_fetch_stage(registry, config.data)
        ctx = await stage.run(make_ctx("https://shop.example/item"))
        assert ctx.response is not None and ctx.response.status == 200
        assert limiter.bucket_for("shop.example").acquired_count == 3  # 1 try + 2 retries

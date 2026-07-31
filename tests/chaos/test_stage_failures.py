"""Chaos tests: a stage raising each error class mid-pipeline gets exactly the
action the config policy prescribes (Plan 03 build list)."""

import pytest

from core.contracts.stage import ErrorAction
from core.errors.exceptions import (
    ExtractionError,
    FetchError,
    ParseError,
    PersistError,
    TransformError,
    ValidationError,
)
from core.errors.policy import policy_from_config
from core.pipeline.context import Context
from core.pipeline.runner import PipelineRunner, PipelineStatus
from tests.fakes import FakeStage

POLICY_CONFIG = {
    "error_policy": {
        "default": "abort",
        "max_retries": 1,
        "stages": {
            "fetch": {"FetchError": "retry"},
            "parse": {"ParseError": "skip"},
            "extract": {"ExtractionError": "quarantine"},
            "validate": {"ValidationError": "quarantine"},
            "transform": {"TransformError": "skip"},
            "persist": {"PersistError": "retry"},
        },
    }
}


def make_ctx() -> Context:
    """Builds a minimal context for chaos tests."""
    return Context(trace_id="chaos", config={}, config_fingerprint="fp")


CASES = [
    # (stage name, error, expected final status, later stage should run?)
    ("fetch", FetchError("net down", transient=True), PipelineStatus.ABORTED, False),
    ("parse", ParseError("bad html"), PipelineStatus.COMPLETED, True),
    ("extract", ExtractionError("spec drift", field="price"), PipelineStatus.QUARANTINED, False),
    ("validate", ValidationError("bad record"), PipelineStatus.QUARANTINED, False),
    ("transform", TransformError("bad date"), PipelineStatus.COMPLETED, True),
    ("persist", PersistError("db down", transient=True), PipelineStatus.ABORTED, False),
]


class TestPolicyAppliedPerErrorClass:
    @pytest.mark.parametrize(
        ("stage_name", "error", "expected_status", "later_runs"),
        CASES,
        ids=[c[0] for c in CASES],
    )
    async def test_mid_pipeline_failure_gets_configured_action(
        self, stage_name, error, expected_status, later_runs
    ):
        """The failing stage sits between two healthy ones; retry cases fail
        past the retry budget so the fallback (abort) is what we observe."""
        log: list[str] = []
        policy = policy_from_config(POLICY_CONFIG)
        stages = [
            FakeStage("first", log),
            FakeStage(stage_name, log, fail_times=99, error=error),
            FakeStage("last", log),
        ]
        result = await PipelineRunner(stages, policy).run(make_ctx())
        assert result.status is expected_status
        assert ("last" in log) is later_runs

    async def test_retry_budget_respected_then_success(self):
        """A transient failure inside the budget recovers and completes."""
        log: list[str] = []
        policy = policy_from_config(POLICY_CONFIG)
        stages = [FakeStage("fetch", log, fail_times=1, error=FetchError("blip", transient=True))]
        result = await PipelineRunner(stages, policy).run(make_ctx())
        assert result.status is PipelineStatus.COMPLETED
        assert log == ["fetch", "fetch"]

    async def test_unknown_error_class_uses_default(self):
        """An error no stage rule mentions falls back to the configured default."""

        class WeirdError(ValueError):
            pass

        class WeirdStage:
            name = "weird"

            async def run(self, ctx):
                raise WeirdError("???")

            def on_error(self, ctx, err):
                return ErrorAction.SKIP  # config is silent → stage fallback wins

        result = await PipelineRunner([WeirdStage()], policy_from_config(POLICY_CONFIG)).run(
            make_ctx()
        )
        assert result.status is PipelineStatus.COMPLETED

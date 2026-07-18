"""Tests for the pipeline runner: ordering, every ErrorAction, timeouts, events."""

import pytest

from components.quarantine.file_sink import FileQuarantineSink
from core.contracts.stage import ErrorAction
from core.errors.exceptions import FetchError, StageTimeoutError, ValidationError
from core.errors.policy import ErrorPolicy
from core.events.bus import EventBus
from core.pipeline.context import Context
from core.pipeline.runner import PipelineRunner, PipelineStatus
from tests.fakes import FakeStage


def make_ctx() -> Context:
    """Builds a minimal context for runner tests."""
    return Context(trace_id="t-1", config={}, config_fingerprint="f-1")


class TestOrderingAndSuccess:
    async def test_stages_run_in_configured_order(self):
        log: list[str] = []
        runner = PipelineRunner(
            [FakeStage(n, log) for n in ["fetch", "parse", "extract"]], ErrorPolicy()
        )
        result = await runner.run(make_ctx())
        assert result.status is PipelineStatus.COMPLETED
        assert log == ["fetch", "parse", "extract"]

    async def test_reordering_stages_is_data_only(self):
        """The same stage objects in a different order run in that order — no code change."""
        log: list[str] = []
        stages = {n: FakeStage(n, log) for n in ["a", "b", "c"]}
        await PipelineRunner([stages["c"], stages["a"], stages["b"]], ErrorPolicy()).run(make_ctx())
        assert log == ["c", "a", "b"]


class TestErrorActions:
    async def test_retry_then_success(self):
        log: list[str] = []
        stage = FakeStage("fetch", log, fail_times=2, error=FetchError("boom", transient=True))
        policy = ErrorPolicy(max_retries=2, stages={"fetch": {"FetchError": ErrorAction.RETRY}})
        result = await PipelineRunner([stage], policy).run(make_ctx())
        assert result.status is PipelineStatus.COMPLETED
        assert log == ["fetch", "fetch", "fetch"]  # 1 try + 2 retries

    async def test_retry_exhausted_falls_back(self):
        log: list[str] = []
        stage = FakeStage("fetch", log, fail_times=99, error=FetchError("down"))
        policy = ErrorPolicy(
            max_retries=1,
            on_retry_exhausted=ErrorAction.ABORT,
            stages={"fetch": {"FetchError": ErrorAction.RETRY}},
        )
        result = await PipelineRunner([stage], policy).run(make_ctx())
        assert result.status is PipelineStatus.ABORTED
        assert result.failed_stage == "fetch"
        assert log == ["fetch", "fetch"]

    async def test_skip_continues_pipeline(self):
        log: list[str] = []
        failing = FakeStage("transform", log, fail_times=1)
        after = FakeStage("persist", log)
        policy = ErrorPolicy(stages={"transform": {"ScraperError": ErrorAction.SKIP}})
        result = await PipelineRunner([failing, after], policy).run(make_ctx())
        assert result.status is PipelineStatus.COMPLETED
        assert log == ["transform", "persist"]

    async def test_quarantine_stops_and_writes_sink(self, tmp_path):
        sink = FileQuarantineSink(tmp_path)
        stage = FakeStage("validate", [], fail_times=1, error=ValidationError("bad record"))
        policy = ErrorPolicy(stages={"validate": {"ValidationError": ErrorAction.QUARANTINE}})
        result = await PipelineRunner([stage], policy, quarantine=sink).run(make_ctx())
        assert result.status is PipelineStatus.QUARANTINED
        content = (tmp_path / "quarantine.jsonl").read_text()
        assert '"stage": "validate"' in content
        assert '"error_type": "ValidationError"' in content
        assert '"trace_id": "t-1"' in content

    async def test_abort_stops_pipeline(self):
        log: list[str] = []
        stages = [FakeStage("fetch", log, fail_times=1), FakeStage("parse", log)]
        result = await PipelineRunner(stages, ErrorPolicy()).run(make_ctx())
        assert result.status is PipelineStatus.ABORTED
        assert log == ["fetch"]  # parse never ran

    async def test_config_policy_beats_stage_fallback(self):
        """Config says SKIP even though the stage's own on_error says ABORT."""
        log: list[str] = []
        stage = FakeStage("extract", log, fail_times=1, on_error_action=ErrorAction.ABORT)
        policy = ErrorPolicy(stages={"extract": {"ScraperError": ErrorAction.SKIP}})
        result = await PipelineRunner([stage], policy).run(make_ctx())
        assert result.status is PipelineStatus.COMPLETED

    async def test_stage_fallback_used_when_config_silent(self):
        stage = FakeStage("extract", [], fail_times=1, on_error_action=ErrorAction.SKIP)
        result = await PipelineRunner([stage], ErrorPolicy()).run(make_ctx())
        assert result.status is PipelineStatus.COMPLETED


class TestTimeout:
    async def test_slow_stage_times_out_as_typed_error(self):
        stage = FakeStage("fetch", [], sleep_s=0.5)
        runner = PipelineRunner([stage], ErrorPolicy(), timeouts={"fetch": 0.05})
        result = await runner.run(make_ctx())
        assert result.status is PipelineStatus.ABORTED
        assert isinstance(result.error, StageTimeoutError)


class TestEvents:
    async def test_stage_events_emitted_with_trace_id(self):
        bus = EventBus()
        seen: list[tuple[str, str]] = []
        bus.subscribe("*", lambda e: seen.append((e.type, str(e.payload.get("stage")))))
        runner = PipelineRunner([FakeStage("fetch", [])], ErrorPolicy(), bus=bus)
        await runner.run(make_ctx())
        assert ("stage.started", "fetch") in seen
        assert ("stage.completed", "fetch") in seen

    async def test_crashing_listener_never_breaks_the_run(self):
        bus = EventBus()

        def bad_listener(event):
            raise RuntimeError("listener bug")

        bus.subscribe("*", bad_listener)
        result = await PipelineRunner([FakeStage("fetch", [])], ErrorPolicy(), bus=bus).run(
            make_ctx()
        )
        assert result.status is PipelineStatus.COMPLETED
        assert bus.listener_errors > 0


class TestUnexpectedErrors:
    async def test_non_scraper_exception_is_wrapped_and_aborts(self):
        class BuggyStage:
            name = "buggy"

            async def run(self, ctx):
                raise KeyError("oops")

            def on_error(self, ctx, err):
                return ErrorAction.ABORT

        result = await PipelineRunner([BuggyStage()], ErrorPolicy()).run(make_ctx())
        assert result.status is PipelineStatus.ABORTED
        assert "unexpected error" in str(result.error)
        with pytest.raises(KeyError):
            raise result.error.__cause__

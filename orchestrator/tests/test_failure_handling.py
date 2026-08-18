"""Tests for orchestrator.error_handling — retry logic and exceptions."""

import time
from unittest.mock import MagicMock

import pytest

from orchestrator.error_handling import (
    LLMCallError,
    NoCriticalDataError,
    PipelineError,
    StageResult,
    StageStatus,
    retry_with_backoff,
)


class TestStageResult:
    def test_basic_creation(self):
        r = StageResult(stage_name="test", status=StageStatus.SUCCESS)
        assert r.stage_name == "test"
        assert r.status == StageStatus.SUCCESS
        assert r.error is None
        assert r.duration_ms == 0.0

    def test_failure_with_error(self):
        r = StageResult(
            stage_name="extraction",
            status=StageStatus.FAILED,
            error="timeout",
            duration_ms=1500.0,
        )
        assert r.error == "timeout"
        assert r.duration_ms == 1500.0


class TestExceptions:
    def test_pipeline_error_has_stage(self):
        err = PipelineError("oops", stage="extraction")
        assert err.stage == "extraction"
        assert str(err) == "oops"

    def test_no_critical_data_is_pipeline_error(self):
        err = NoCriticalDataError("no docs", stage="ingestion")
        assert isinstance(err, PipelineError)

    def test_llm_call_error_is_pipeline_error(self):
        err = LLMCallError("timeout", stage="summary")
        assert isinstance(err, PipelineError)


class TestRetryWithBackoff:
    def test_succeeds_first_try(self):
        mock_fn = MagicMock(return_value="ok")
        decorated = retry_with_backoff(max_retries=3, base_delay=0.01)(mock_fn)
        assert decorated() == "ok"
        assert mock_fn.call_count == 1

    def test_succeeds_after_retries(self):
        mock_fn = MagicMock(side_effect=[ValueError("fail"), ValueError("fail"), "ok"])
        decorated = retry_with_backoff(
            max_retries=3, base_delay=0.01, retryable_exceptions=(ValueError,)
        )(mock_fn)
        assert decorated() == "ok"
        assert mock_fn.call_count == 3

    def test_exhausts_retries_and_raises(self):
        mock_fn = MagicMock(side_effect=ValueError("always fails"))
        decorated = retry_with_backoff(
            max_retries=2, base_delay=0.01, retryable_exceptions=(ValueError,)
        )(mock_fn)
        with pytest.raises(LLMCallError):
            decorated()
        assert mock_fn.call_count == 3  # 1 initial + 2 retries

    def test_non_retryable_exception_raises_immediately(self):
        mock_fn = MagicMock(side_effect=TypeError("bad type"))
        decorated = retry_with_backoff(
            max_retries=3, base_delay=0.01, retryable_exceptions=(ValueError,)
        )(mock_fn)
        with pytest.raises(TypeError):
            decorated()
        assert mock_fn.call_count == 1

    def test_backoff_increases_delay(self):
        calls: list[float] = []

        def failing_fn():
            calls.append(time.time())
            raise ValueError("fail")

        decorated = retry_with_backoff(
            max_retries=2, base_delay=0.05, retryable_exceptions=(ValueError,)
        )(failing_fn)

        with pytest.raises(LLMCallError):
            decorated()

        assert len(calls) == 3
        # Second gap should be roughly 2x the first
        gap1 = calls[1] - calls[0]
        gap2 = calls[2] - calls[1]
        assert gap2 > gap1 * 1.5  # allow some tolerance

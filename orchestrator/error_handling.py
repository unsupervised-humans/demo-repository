"""Error handling, retry logic, and custom exceptions for the orchestrator.

Provides:
- ``retry_with_backoff`` — decorator for LLM / external API calls.
- ``StageResult`` — per-stage execution result record.
- ``PipelineError`` hierarchy — typed exceptions for pipeline failures.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ── Stage result ──────────────────────────────────────────────────────────────


class StageStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Record of a single pipeline stage execution."""

    stage_name: str
    status: StageStatus
    error: str | None = None
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


# ── Custom exceptions ────────────────────────────────────────────────────────


class PipelineError(Exception):
    """Base exception for all orchestrator pipeline errors."""

    def __init__(self, message: str, stage: str | None = None):
        self.stage = stage
        super().__init__(message)


class StageFailedError(PipelineError):
    """A pipeline stage failed fatally."""


class NoCriticalDataError(PipelineError):
    """A required prerequisite is missing (e.g. zero documents)."""


class LLMCallError(PipelineError):
    """An LLM API call failed after exhausting retries."""


# ── Retry with exponential backoff ────────────────────────────────────────────


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator: retry a function with exponential backoff.

    Parameters
    ----------
    max_retries : int
        Maximum number of retry attempts (not counting the first call).
    base_delay : float
        Initial delay in seconds between retries.
    max_delay : float
        Cap on delay between retries.
    retryable_exceptions : tuple
        Exception types that trigger a retry. Deterministic errors
        (e.g. ``ValueError``) should generally NOT be retried.

    Usage
    -----
    ::

        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def call_grok(prompt):
            ...
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), max_delay)
                        logger.warning(
                            "Retry %d/%d for %s after %.1fs — %s: %s",
                            attempt + 1,
                            max_retries,
                            getattr(fn, "__name__", repr(fn)),
                            delay,
                            type(exc).__name__,
                            exc,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d retries exhausted for %s: %s",
                            max_retries,
                            getattr(fn, "__name__", repr(fn)),
                            exc,
                        )
            raise LLMCallError(
                f"Failed after {max_retries} retries: {last_exc}",
                stage=getattr(fn, "__name__", repr(fn)),
            )

        return wrapper

    return decorator

"""Shared fixtures and factories for benchmark_pipeline's colocated tests."""

from datetime import UTC, datetime

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    BenchmarkTask,
    Difficulty,
    Iso8601Utc,
    RequiredTerms,
    TaskOrigin,
)


def make_task(  # noqa: PLR0913  # test builder must expose every unit-relevant field
    *,
    task_id: str = "task-1",
    question: str = "What is the capital of France?",
    category: str = "geography",
    golden_answer: str | None = "Paris",
    cosine_enabled: bool = True,
    required_terms: RequiredTerms | None = None,
    task_origin: TaskOrigin = TaskOrigin.FILE,
) -> BenchmarkTask:
    """Build a minimal, valid `BenchmarkTask` for a pipeline unit test."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=task_origin,
        cosine_enabled=cosine_enabled,
        question=question,
        category=category,
        golden_answer=golden_answer,
        difficulty=Difficulty.MEDIUM,
        required_terms=required_terms if required_terms is not None else RequiredTerms(),
    )


class FakeClock:
    """A minimal, fully controllable `Clock` double (matches the project-wide
    per-module convention already used by `backend/evaluation/tests/conftest.py`).
    """

    def __init__(self, *, start_monotonic_ms: int = 0) -> None:
        self._monotonic_ms = start_monotonic_ms
        self._now = datetime(2026, 1, 1, tzinfo=UTC)

    def now_utc(self) -> Iso8601Utc:
        return self._now.isoformat()

    def monotonic_ms(self) -> int:
        return self._monotonic_ms


def make_cancellation_token() -> CancellationToken:
    """Build a fresh, uncancelled `CancellationToken` backed by a `FakeClock`."""
    return CancellationToken(clock=FakeClock())

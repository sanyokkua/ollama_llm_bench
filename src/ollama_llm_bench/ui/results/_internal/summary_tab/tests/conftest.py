"""Builders for ``BenchmarkResult``/``BenchmarkTask`` fixtures used by
``test_select.py`` (STORY-062). Mirrors
``backend/benchmark_pipeline/tests/conftest.py``'s builder-function pattern; field
names verified against ``backend/domain/models.py`` directly.
"""

from ollama_llm_bench.backend.domain import (
    AttemptOutcome,
    BenchmarkResult,
    BenchmarkResultAttempt,
    BenchmarkTask,
    Difficulty,
    RequiredTerms,
    ResolutionLayer,
    ResultStatus,
    TaskOrigin,
    Verdict,
)

__all__: list[str] = ["make_result", "make_task"]

_CREATED_AT = "2026-01-01T00:00:00+00:00"


def make_task(  # noqa: PLR0913  # test builder must expose every aggregation-relevant field
    *,
    task_id: str = "task-1",
    question: str = "What is the capital of France?",
    category: str = "geography",
    golden_answer: str | None = "Paris",
    cosine_enabled: bool = True,
    difficulty: Difficulty = Difficulty.MEDIUM,
) -> BenchmarkTask:
    """Build a minimal, valid ``BenchmarkTask`` for a Summary-aggregation test."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=TaskOrigin.FILE,
        cosine_enabled=cosine_enabled,
        question=question,
        category=category,
        golden_answer=golden_answer,
        difficulty=difficulty,
        required_terms=RequiredTerms(),
    )


def make_result(  # noqa: PLR0913  # test builder must expose every aggregation-relevant field
    *,
    result_id: int = 1,
    run_id: int = 1,
    task_id: str = "task-1",
    provider_id: str = "provider-1",
    provider_name: str = "Ollama Local",
    model_name: str = "llama3.2:3b",
    status: ResultStatus = ResultStatus.COMPLETED,
    verdict: Verdict | None = None,
    total_time_ms: int | None = 1000,
    ttft_ms: int | None = 100,
    completion_tokens: int | None = 50,
    tokens_per_second: float | None = 20.0,
    tokens_estimated: bool = False,
    has_thinking_block: bool = False,
    judge_verdict: Verdict | None = None,
    cosine_similarity: float | None = None,
    resolution_layer: ResolutionLayer | None = None,
    attempts_count: int = 1,
) -> BenchmarkResult:
    """Build a minimal, valid ``BenchmarkResult`` for a Summary-aggregation test."""
    return BenchmarkResult(
        result_id=result_id,
        run_id=run_id,
        task_id=task_id,
        provider_id=provider_id,
        provider_name=provider_name,
        model_name=model_name,
        status=status,
        verdict=verdict,
        created_at=_CREATED_AT,
        total_time_ms=total_time_ms,
        ttft_ms=ttft_ms,
        completion_tokens=completion_tokens,
        tokens_per_second=tokens_per_second,
        tokens_estimated=tokens_estimated,
        has_thinking_block=has_thinking_block,
        judge_verdict=judge_verdict,
        cosine_similarity=cosine_similarity,
        resolution_layer=resolution_layer,
        attempts=tuple(_make_attempt(index) for index in range(1, attempts_count + 1)),
    )


def _make_attempt(attempt_index: int) -> BenchmarkResultAttempt:
    return BenchmarkResultAttempt(
        attempt_index=attempt_index,
        timeout_ms=30000,
        duration_ms=500,
        outcome=AttemptOutcome.SUCCESS,
    )

"""Shared test builders for the Details tab's pure select.py tests.

Field names verified against ``backend/domain/models.py`` directly (STORY-063 task 2);
mirrors ``ui/results/_internal/summary_tab/tests/conftest.py``'s builder-function
pattern from STORY-062.
"""

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    ResolutionLayer,
    ResultStatus,
    TaskOrigin,
    Verdict,
)

__all__: list[str] = ["make_result", "make_task"]

_CREATED_AT = "2026-07-20T00:00:00Z"


def make_result(  # noqa: PLR0913 -- test builder must expose every mapped field
    *,
    result_id: int = 1,
    run_id: int = 1,
    task_id: str = "task-1",
    provider_id: str = "prov-a",
    provider_name: str = "Ollama Local",
    model_name: str = "llama3",
    status: ResultStatus = ResultStatus.COMPLETED,
    verdict: Verdict | None = None,
    ttft_ms: int | None = 120,
    total_time_ms: int | None = 900,
    completion_tokens: int | None = 42,
    tokens_per_second: float | None = 10.5,
    tokens_estimated: bool = False,
    cosine_similarity: float | None = None,
    keyword_verdict: Verdict | None = None,
    cosine_verdict: Verdict | None = None,
    judge_verdict: Verdict | None = None,
    resolution_layer: ResolutionLayer | None = None,
    judge_reasoning: str | None = None,
    error_message: str | None = None,
) -> BenchmarkResult:
    """Build a minimal, valid ``BenchmarkResult`` for a Details-tab select.py test."""
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
        ttft_ms=ttft_ms,
        total_time_ms=total_time_ms,
        completion_tokens=completion_tokens,
        tokens_per_second=tokens_per_second,
        tokens_estimated=tokens_estimated,
        cosine_similarity=cosine_similarity,
        keyword_verdict=keyword_verdict,
        cosine_verdict=cosine_verdict,
        judge_verdict=judge_verdict,
        resolution_layer=resolution_layer,
        judge_reasoning=judge_reasoning,
        error_message=error_message,
    )


def make_task(  # noqa: PLR0913 -- test builder must expose every mapped field
    *,
    task_id: str = "task-1",
    category: str = "reasoning",
    sub_category: str = "logic",
    difficulty: Difficulty = Difficulty.MEDIUM,
    task_origin: TaskOrigin = TaskOrigin.FILE,
    golden_answer: str | None = "The answer is 42.",
) -> BenchmarkTask:
    """Build a minimal, valid ``BenchmarkTask`` for a Details-tab select.py test."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=task_origin,
        question="What is the answer?",
        category=category,
        sub_category=sub_category,
        difficulty=difficulty,
        golden_answer=golden_answer,
    )

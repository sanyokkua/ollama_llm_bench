"""Shared test builder helpers for `backend/charts/tests/`."""

import uuid

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    ResultStatus,
    TaskOrigin,
    Verdict,
)

__all__ = ["make_benchmark_result", "make_benchmark_task", "make_provider_id"]


def make_provider_id() -> str:
    """Build a syntactically valid UUID4 provider id for a test fixture."""
    return str(uuid.uuid4())


def make_benchmark_task(
    *,
    task_id: str = "factual_capitals_france",
    category: str = "General Knowledge",
    difficulty: Difficulty = Difficulty.EASY,
    task_order: int = 0,
    question: str = "What is the capital of France?",
) -> BenchmarkTask:
    """Build a valid `BenchmarkTask` for a test fixture."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=TaskOrigin.FILE,
        question=question,
        category=category,
        difficulty=difficulty,
        task_order=task_order,
    )


def make_benchmark_result(  # noqa: PLR0913  # test builder must expose every chart-relevant field
    *,
    result_id: int = 1,
    run_id: int = 3,
    task_id: str = "factual_capitals_france",
    provider_id: str | None = None,
    provider_name: str = "ollama_local",
    model_name: str = "llama3.2:3b",
    status: ResultStatus = ResultStatus.COMPLETED,
    verdict: Verdict | None = None,
    ttft_ms: int | None = 120,
    total_time_ms: int | None = 3870,
    completion_tokens: int | None = 220,
    tokens_per_second: float | None = 58.2,
    tokens_estimated: bool = False,
    has_thinking_block: bool = False,
    cosine_similarity: float | None = None,
) -> BenchmarkResult:
    """Build a valid, chart-relevant `BenchmarkResult` for a test fixture."""
    return BenchmarkResult(
        result_id=result_id,
        run_id=run_id,
        task_id=task_id,
        provider_id=provider_id or make_provider_id(),
        provider_name=provider_name,
        model_name=model_name,
        status=status,
        verdict=verdict,
        created_at="2026-05-16T15:00:00Z",
        ttft_ms=ttft_ms,
        total_time_ms=total_time_ms,
        completion_tokens=completion_tokens,
        tokens_per_second=tokens_per_second,
        tokens_estimated=tokens_estimated,
        has_thinking_block=has_thinking_block,
        cosine_similarity=cosine_similarity,
    )

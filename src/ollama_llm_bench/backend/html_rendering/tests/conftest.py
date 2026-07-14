"""Shared test helpers for backend/html_rendering/tests/."""

import uuid

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    ResultStatus,
    TaskOrigin,
)

__all__ = ["make_benchmark_result", "make_benchmark_task"]


def make_provider_id() -> str:
    """Build a syntactically valid UUID4 provider id for a test fixture."""
    return str(uuid.uuid4())


def make_benchmark_task(
    *,
    task_id: str = "factual_capitals_france",
    category: str = "General Knowledge",
    sub_category: str = "Geography",
    difficulty: Difficulty = Difficulty.EASY,
    question: str = "What is the capital of France?",
) -> BenchmarkTask:
    """Build a valid `BenchmarkTask` for a test fixture."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=TaskOrigin.FILE,
        question=question,
        category=category,
        sub_category=sub_category,
        difficulty=difficulty,
    )


def make_benchmark_result(
    *,
    task_id: str = "factual_capitals_france",
    sanitized_response: str | None = "Paris",
    status: ResultStatus = ResultStatus.COMPLETED,
) -> BenchmarkResult:
    """Build a valid `BenchmarkResult` for a test fixture."""
    return BenchmarkResult(
        result_id=1,
        run_id=3,
        task_id=task_id,
        provider_id=make_provider_id(),
        provider_name="ollama_local",
        model_name="llama3.2:3b",
        status=status,
        created_at="2026-05-16T15:00:00Z",
        sanitized_response=sanitized_response,
    )

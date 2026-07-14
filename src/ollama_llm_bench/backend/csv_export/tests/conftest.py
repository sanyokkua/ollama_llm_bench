"""Shared test helpers for backend/csv_export/tests/."""

import uuid

from ollama_llm_bench.backend.csv_export import RunExportContext, SummaryRow
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    ResultStatus,
    RunMode,
    TaskOrigin,
)

__all__ = [
    "make_benchmark_result",
    "make_benchmark_task",
    "make_export_context",
    "make_summary_row",
]


def make_provider_id() -> str:
    """Build a syntactically valid UUID4 provider id for a test fixture."""
    return str(uuid.uuid4())


def make_export_context(*, run_mode: RunMode = RunMode.GRADED) -> RunExportContext:
    """Build a valid `RunExportContext` for a test fixture."""
    return RunExportContext(
        run_id=3,
        effective_run_name="Graded Benchmark 2026-05-16 14:53",
        run_mode=run_mode,
        exported_at="2026-05-16T15:04:22Z",
        app_version="1.0.0",
    )


def make_summary_row(
    *,
    provider_name: str = "ollama_local",
    model_name: str = "llama3.2:3b",
    avg_score: float | None = None,
) -> SummaryRow:
    """Build a valid `SummaryRow` for a test fixture; `avg_score` defaults to the
    reserved-column `None` every real caller supplies (the app has no judge score)."""
    return SummaryRow(
        provider_id=make_provider_id(),
        provider_name=provider_name,
        model_name=model_name,
        task_count=10,
        completed_count=10,
        passed_count=7,
        failed_count=3,
        pass_rate=0.700,
        avg_score=avg_score,
        avg_cosine=0.681,
        avg_ttft_s=0.412,
        avg_total_time_s=3.870,
        avg_tps=58.20,
        error_count=0,
    )


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
    error_message: str | None = None,
    status: ResultStatus = ResultStatus.COMPLETED,
    provider_name: str = "ollama_local",
) -> BenchmarkResult:
    """Build a valid `BenchmarkResult` for a test fixture."""
    return BenchmarkResult(
        result_id=1,
        run_id=3,
        task_id=task_id,
        provider_id=make_provider_id(),
        provider_name=provider_name,
        model_name="llama3.2:3b",
        status=status,
        created_at="2026-05-16T15:00:00Z",
        sanitized_response=sanitized_response,
        error_message=error_message,
    )

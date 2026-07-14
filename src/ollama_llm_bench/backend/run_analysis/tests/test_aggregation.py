"""Proves: STORY-035-AC-6 (digest feeds the mode-aware prompt)"""

import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkTask,
    ModelRole,
    ResultStatus,
    RunMode,
    RunStatus,
    TaskOrigin,
    Verdict,
)
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.run_analysis._internal.aggregation import build_run_digest

_NOTABLE_RESULTS_CAP = 12


def _make_result(
    *, result_id: int, task_id: str, provider_id: str, model_name: str, verdict: Verdict | None
) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=result_id,
        run_id=1,
        task_id=task_id,
        provider_id=provider_id,
        provider_name=provider_id,
        model_name=model_name,
        status=ResultStatus.COMPLETED,
        verdict=verdict,
        created_at="2026-01-01T00:00:00Z",
        ttft_ms=100,
        total_time_ms=500,
        tokens_per_second=20.0,
    )


def _make_run(*, models: tuple[BenchmarkRunModelEntry, ...]) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=1,
        run_name="r",
        timestamp="2026-01-01T00:00:00Z",
        run_mode=RunMode.GRADED,
        status=RunStatus.COMPLETED,
        total_tasks=1,
        completed_tasks=1,
        total_elapsed_ms=1000,
        schema_version=1,
        created_at="2026-01-01T00:00:00Z",
        models=models,
    )


def test_all_models_failed_task_is_flagged_notable() -> None:
    """Proves: STORY-035-AC-6 (digest feeds the mode-aware prompt)

    A task every benchmarked model FAILed (>=2 models) is surfaced in the digest's
    notable-results shortlist with the miscalibration hint (SPEC-107).
    """
    task = BenchmarkTask(task_id="t1", task_origin=TaskOrigin.FILE, question="q?")
    run = _make_run(
        models=(
            BenchmarkRunModelEntry(role=ModelRole.TEST, provider_id="p1", model_name="m1"),
            BenchmarkRunModelEntry(role=ModelRole.TEST, provider_id="p1", model_name="m2"),
        )
    )
    results = (
        _make_result(
            result_id=1, task_id="t1", provider_id="p1", model_name="m1", verdict=Verdict.FAIL
        ),
        _make_result(
            result_id=2, task_id="t1", provider_id="p1", model_name="m2", verdict=Verdict.FAIL
        ),
    )
    digest = build_run_digest(run=run, results=results, tasks_by_id={"t1": task})
    assert any(
        entry.task_id == "t1" and "may be mis-specified" in entry.note
        for entry in digest.notable_results
    )


def test_aggregation_is_deterministic() -> None:
    """Proves: RA-18

    The aggregation step is deterministic: identical inputs yield an equal digest.
    """
    task = BenchmarkTask(task_id="t1", task_origin=TaskOrigin.FILE, question="q?")
    run = _make_run(
        models=(BenchmarkRunModelEntry(role=ModelRole.TEST, provider_id="p1", model_name="m1"),)
    )
    results = (
        _make_result(
            result_id=1, task_id="t1", provider_id="p1", model_name="m1", verdict=Verdict.PASS
        ),
    )
    tasks_by_id = {"t1": task}

    first = build_run_digest(run=run, results=results, tasks_by_id=tasks_by_id)
    second = build_run_digest(run=run, results=results, tasks_by_id=tasks_by_id)

    assert first == second


def test_notable_results_shortlist_is_bounded() -> None:
    """Proves: RA-14

    A run with more raw failures than the notable-results cap yields a bounded
    shortlist, not every raw result.
    """
    model_entry = BenchmarkRunModelEntry(role=ModelRole.TEST, provider_id="p1", model_name="m1")
    run = _make_run(models=(model_entry,))
    task_count = _NOTABLE_RESULTS_CAP + 5
    tasks_by_id = {
        f"t{i}": BenchmarkTask(task_id=f"t{i}", task_origin=TaskOrigin.FILE, question="q?")
        for i in range(task_count)
    }
    results = tuple(
        _make_result(
            result_id=i, task_id=f"t{i}", provider_id="p1", model_name="m1", verdict=Verdict.FAIL
        )
        for i in range(task_count)
    )

    digest = build_run_digest(run=run, results=results, tasks_by_id=tasks_by_id)

    assert len(digest.notable_results) <= _NOTABLE_RESULTS_CAP


def test_missing_task_metadata_raises_contract_violation() -> None:
    """Proves: RA-15

    A `task_id` in `results` absent from `tasks_by_id` raises during aggregation.
    """
    run = _make_run(
        models=(BenchmarkRunModelEntry(role=ModelRole.TEST, provider_id="p1", model_name="m1"),)
    )
    results = (
        _make_result(
            result_id=1, task_id="missing", provider_id="p1", model_name="m1", verdict=None
        ),
    )

    with pytest.raises(ContractViolationError):
        build_run_digest(run=run, results=results, tasks_by_id={})
